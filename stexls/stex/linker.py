from typing import List, Dict, Tuple, Set, Iterator, Optional, OrderedDict, Pattern
from pathlib import Path
from itertools import chain
import os, functools
import multiprocessing
import difflib
from collections import defaultdict
from stexls.util.file_watcher import WorkspaceWatcher
from stexls.util.vscode import *
from .parser import ParsedFile
from .compiler import StexObject
from .symbols import Symbol
from .exceptions import *
import pkg_resources

__all__ = ['Linker']

class Linker:
    def __init__(
        self,
        root: Path = '.',
        include: Pattern = None,
        ignore: Pattern = None):
        self.root = Path(root).resolve().absolute()
        if not self.root.is_dir():
            raise ValueError(f'Linker root "{self.root}" is not a directory.')
        self.watcher = WorkspaceWatcher((self.root / '**' / '*.tex').as_posix(), include=include, ignore=ignore)
        self.objects: Dict[Path, List[StexObject]] = {}
        self.module_index: Dict[Path, Dict[str, StexObject]] = {}
        self.build_orders: Dict[StexObject, OrderedDict[StexObject, bool]] = {}
        self.links: Dict[StexObject, StexObject] = {}
        self.changes = None
        self.lazy_build_order_update = False
        self.version = pkg_resources.require("stexls")[0].version

    def get_relevant_objects(self, file: Path, line: int, column: int) -> Iterator[StexObject]:
        file = Path(file).as_uri()
        if file not in self.objects:
            raise ValueError(f'File not found: "{file}"')
        for object in self.objects[file]:
            if object.module:
                for module in object.symbol_table.get(object.module, ()):
                    if module.full_range.contains(Position(line, column)):
                        if object in self.links:
                            yield self.links[object]
            else:
                if object in self.links:
                    yield self.links[object]

    def get_definitions(self, file: Path, line: int, column: int) -> Tuple[List[Range], List[Symbol]]:
        references = []
        definitions = []
        position = Position(line, column)
        for object in self.get_relevant_objects(Path(file).as_uri(), line, column):
            for id, symbols in object.symbol_table.items():
                for symbol in symbols:
                    if symbol.location.contains(position) and symbol not in definitions:
                        references.append(symbol.location.range)
                        definitions.append(symbol)
            for path, ranges in object.references.items():
                for range, id in ranges.items():
                    if not range.contains(position):
                        continue
                    for symbol in object.symbol_table.get(id, ()):
                        if symbol not in definitions:
                            references.append(range)
                            definitions.append(symbol)
        return references, definitions

    def get_references(self, symbol: Symbol) -> List[Location]:
        references = []
        for path, objects in self.objects.items():
            for object in objects:
                for range, id in object.references.get(symbol.location.uri, {}).items():
                    if symbol.identifier == id:
                        references.append(Location(path, range))
        return references

    def view_import_graph(self, file: Path, module_name: str = None, display_symbols: bool = False):
        try:
            import matplotlib
        except ImportError:
            raise ImportError('matplotlib required: "pip install matplotlib" to use this functionality.')
        try:
            from graphviz import Digraph
        except ImportError:
            raise ImportError('graphviz required: "pip install graphviz" to use this functionality.')
        G = Digraph()
        edges = dict()
        found = False
        for object in self.objects.get(Path(file).as_uri(), ()):
            if module_name and (not object.module or object.module != module_name):
                continue
            found = True
            for o in self.build_orders[object]:
                origin = str(o.module.identifier if o.module else o.path)
                if origin in edges:
                    continue
                G.node(origin)
                if display_symbols:
                    for id in o.symbol_table:
                        edges.setdefault(origin, set()).add(id.identifier + '/symbol')
                for module, paths in o.dependencies.items():
                    for path, locations in paths.items():
                        for location, _ in locations.items():
                            edges.setdefault(origin, set()).add(module.identifier)
        if not found:
            raise ValueError('No object found.')
        for origin, targets in edges.items():
            for target in targets:
                G.edge(origin, target)
        G.view(directory='/tmp/stexls')
    
    def info(self, path: Path) -> Iterator[str]:
        path = path if isinstance(path, Path) else Path(path)
        for object in self.objects.get(path, ()):
            link: StexObject = self.links.get(object, object)
            print(link.format())

    def update(self, progressfn=None, use_multiprocessing: bool = True):
        """ Updates the linker.

        Parameters:
            progressfn: Optional function which takes an iterator and a description and returns an identity iterator which tracks progress.
            use_multiprocessing: Enables multiprocessing with the default number of processes.
        
        Returns:
            List of errors occured during linking.
        """
        version = pkg_resources.require('stexls')[0].version
        if self.version != version:
            raise ValueError(f'This linker was created with a different version "{self.version}": Current version is "{version}". Delete the cache to resolve this.')
        progressfn = progressfn or (lambda x, _: x)
        self.changes = self.watcher.update()
        changed_files = self._gather_changed_files()
        with multiprocessing.Pool() as pool:
            mapfn = pool.map if use_multiprocessing else map

            parsed = {
                file: parsed
                for file, parsed
                in zip(
                    changed_files,
                    mapfn(ParsedFile.parse, progressfn(list(map(ParsedFile, changed_files)), "Parsing"))
                )
                if parsed
            }

            compiled = {
                file: objects
                for file, objects
                in zip(
                    parsed.keys(),
                    mapfn(functools.partial(StexObject.compile, self.root), progressfn(parsed.values(), "Compiling"))
                )
                if objects
            }

            modules = {
                file: {
                    object.module: object
                    for object in objects
                    if object.module
                }
                for file, objects in compiled.items()
            }

            removed_files = self._gather_removed_files()
            removed_objects = self._gather_removed_objects(removed_files)
            changed_objects = self._gather_changed_objects(changed_files)
            changed_build_orders = self._gather_changed_build_orders(modules, changed_objects, removed_objects)

            self._cleanup(
                removed_files,
                changed_files,
                removed_objects,
                changed_objects,
                changed_build_orders)

            self.module_index.update(modules)

            self.objects.update(compiled)

            changed_links = changed_build_orders | set(
                object
                for objects in compiled.values()
                for object in objects)

            links: Dict[StexObject, StexObject] = {
                object: StexObject(self.root)
                for object in changed_links
            }

            _build_orders = list(map(
                lambda obj: Linker._make_build_order(
                    current=obj,
                    module_index=self.module_index,
                    errors=links[obj].errors,
                    root=obj),
                progressfn(changed_links, "Resolving Dependencies")
            ))

            assert len(changed_links) == len(_build_orders)
            build_orders: Dict[StexObject, List[StexObject]] = dict(zip(changed_links, _build_orders))
            
            self.build_orders.update(build_orders)

            assert len(links.values()) == len(build_orders.values())
            args = progressfn(list(zip(links.values(), build_orders.values())), "Linking")
            if use_multiprocessing and len(links.values()) != 0 and len(build_orders.values()) != 0:
                links: List[StexObject] = pool.starmap(StexObject.link_list, args)
            else:
                links: List[StexObject] = [
                    l.link_list(order)
                    for l, order
                    in args
                ]
        
        links: Dict[StexObject, StexObject] = dict(zip(changed_links, links))

        self.links.update(links)

    @staticmethod
    def _make_build_order(
        current: StexObject,
        module_index: Dict[Path, Dict[str, StexObject]],
        errors: Dict[Location, List[Exception]]=None,
        build_order_cache: Dict[StexObject, List[StexObject]] = None,
        cyclic_stack: OrderedDict[StexObject, Location] = None,
        at_toplevel: bool = True,
        usemodule_on_stack: bool = False,
        root: StexObject = None) -> List[StexObject]:
        """ Recursively creates the build order for a root object. """

        # create default values if none are given
        build_order_cache = dict() if build_order_cache is None else build_order_cache
        cyclic_stack: OrderedDict[StexObject, Location] = OrderedDict() if cyclic_stack is None else cyclic_stack

        # check if the build order for the current not was created yet
        if current not in build_order_cache:
            # new build order
            build_order: List[StexObject] = list()

            # check all dependencies
            for module, files in current.dependencies.items():
                for path, locations in files.items():
                    # ignore not indexed files or if the file does not contain the module
                    if path not in module_index:
                        if at_toplevel:
                            e = LinkError(f'Not a file: "{path}" does not exist or does not export any modules.')
                            for location in locations:
                                errors[location].append(e)
                        continue

                    if module not in module_index[path]:
                        if at_toplevel:
                            e = LinkError(f'Imported module not exported: "{module.identifier}" is not exported by "{path}"')
                            for location in locations:
                                errors[location].append(e)
                        continue

                    object = module_index[path][module]

                    # Warning for multiple imports of same module
                    import_locations = list(locations)
                    if at_toplevel and len(import_locations) > 1:
                        first_import = import_locations[0].range.start.translate(1, 1).format()
                        for import_location in import_locations[1:]:
                            e = LinkWarning(f'Multiple imports of module "{module.identifier}" in this file, first imported in {first_import}.')
                            errors.setdefault(import_location, []).append(e)

                    # For each import location
                    for location, (public, _) in locations.items():
                        # ignore all private imports that are not done by the toplevel root
                        if not public and not at_toplevel:
                            continue

                        # If a importmodule of the root is done while the stack is marked as "usemodule used", ignore the import
                        if usemodule_on_stack and object == root:
                            continue

                        # Check if cycle created 
                        if object in cyclic_stack:
                            cycle = list(cyclic_stack.items())
                            cycle_end_module, cycle_end = cycle[-1]
                            # Create error only if we are at the toplevel for a clean diagnostic report
                            if not at_toplevel and cycle_end_module == root:
                                cycle_module, cycle_start = cycle[0]
                                errors[cycle_start].append(
                                    LinkError(f'Cyclic dependency: Import of "{cycle_module.module.identifier}" creates cycle at "{cycle_end.format_link()}"'))
                            # always ignore this import to prevent infinite loops
                            continue

                        # Stack the child at the current location and compute it's build order
                        cyclic_stack[object] = location
                        child_build_order: List[StexObject] = Linker._make_build_order(
                            current=object, # next object
                            module_index=module_index, # inherit
                            errors=errors, # inherit
                            build_order_cache=build_order_cache, # inherit
                            cyclic_stack=cyclic_stack, # inherit
                            # only the toplevel call _make_build_order can do certain things
                            at_toplevel=False,
                            root=root, # inherit
                            # mark child as used if any import in the stack is imported via "usemodule"
                            usemodule_on_stack=usemodule_on_stack or not public)
                        del cyclic_stack[object]

                        # remove duplicates
                        for child in child_build_order:
                            while child in build_order:
                                build_order.remove(child)

                        # Move all imports from the child to the front
                        build_order = child_build_order + build_order
            # cache the current object
            build_order_cache[current] = build_order + [current]
        # return cached build order
        return build_order_cache[current]

    def _gather_removed_files(self) -> Set[Path]:
        ' Returns set of files that were removed from the workspace. '
        return self.changes.deleted

    def _gather_changed_files(self) -> Set[Path]:
        ' Returns set of files which were created or modified. '
        return self.changes.created | self.changes.modified

    def _gather_removed_objects(
        self,
        removed_files: Set[Path]) -> Set[StexObject]:
        ' Returns set of objects which are removed because their file was deleted. '
        return set(
            object
            for file
            in removed_files
            for object in self.objects.get(file, ()))

    def _gather_changed_objects(
        self,
        changed_files: Set[Path]) -> Set[StexObject]:
        """ Returns set of objects which changed because the file they originate from was modified.

        Parameters:
            changed_files: Set of files which were modified compared to the last update.
        """
        return set(
            object1
            for file in changed_files
            for object1 in self.objects.get(file, ())
        )

    def _gather_changed_build_orders(
        self,
        modules: Dict[Path, Dict[str, StexObject]],
        changed_objects: Set[StexObject],
        removed_objects: Set[StexObject]) -> Set[StexObject]:
        ' Returns set of objects whose build order is out-of-date because an object in the build order was changed or removed. '
        if self.lazy_build_order_update:
            removed_objects = set((r.path, r.module) for r in removed_objects)
            changed_objects = set(
                (changed.path, changed.module)
                for changed in changed_objects
                if changed.module
                and modules.get(changed.path).get(changed.module).is_object_changed(changed)
            )
        else:
            removed_objects = set((r.path, r.module) for r in removed_objects)
            changed_objects = set((c.path, c.module) for c in changed_objects)
        changed_or_removed = changed_objects | removed_objects
        changed_build_orders =  set(
            object
            for object, order in self.build_orders.items() # check for each build order currently listed
            if (object.path, object.module) not in changed_or_removed # if the object itself is not already being removed
            and not set((o.path, o.module) for o in order).isdisjoint(changed_or_removed) # mark it changed because the build order and set of changed or removed object is NOT disjoint
        )
        return changed_build_orders

    def _cleanup(
        self,
        removed_files: Set[Path],
        changed_files: Set[Path],
        removed_objects: Set[StexObject],
        changed_objects: Set[StexObject],
        changed_build_orders: Set[StexObject]):
        ' Cleans the dictionaries from delete files/objects and objects which will be changed during the next update. '
        for path in (removed_files | changed_files):
            if path in self.objects:
                del self.objects[path]
            if path in self.module_index:
                del self.module_index[path]
            if path in self.links:
                del self.links[path]
        for object in (removed_objects | changed_objects | changed_build_orders):
            if object in self.build_orders:
                del self.build_orders[object]
            if object in self.links:
                del self.links[object]
