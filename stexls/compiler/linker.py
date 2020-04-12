from typing import List, Dict, Tuple, Set, Iterator, Optional, OrderedDict, Pattern
from pathlib import Path
from itertools import chain
import os, functools
import multiprocessing
from stexls.util.location import Location, Position
from stexls.util.file_watcher import WorkspaceWatcher
from .parser import ParsedFile
from .compiler import StexObject
from .exceptions import *

__all__ = ['Linker']

class Linker:
    def __init__(self, root: Path = '.', file_pattern: 'glob' = '**/*.tex', ignore: Pattern = None):
        self.root = Path(root).resolve().absolute()
        assert self.root.is_dir()
        self.watcher = WorkspaceWatcher(os.path.join(root, file_pattern), ignore=ignore)
        self.objects: Dict[Path, List[StexObject]] = {}
        self.module_index: Dict[Path, Dict[str, StexObject]] = {}
        self.build_orders: Dict[StexObject, OrderedDict[StexObject, bool]] = {}
        self.links: Dict[StexObject, StexObject] = {}
        self.changes = None
        self.lazy_build_order_update = True

    def get_relevant_objects(self, file: Path, line: int, column: int) -> Iterator[StexObject]:
        file = Path(file)
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
        for object in self.objects.get(Path(file), ()):
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
            progressfn: Optional function which returns it's argument and can be used to track progressfn.
            use_multiprocessing: Enables multiprocessing with the default number of processes.
        
        Returns:
            List of errors occured during linking.
        """
        progressfn = progressfn or (lambda x: x)
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

            new_build_orders = {
                object: list(Linker._make_build_order(
                        root=object,
                        module_index=self.module_index,
                        build_order_cache=self.build_orders))
                for object in progressfn(changed_links, "Building")}

            links = mapfn(self.link, progressfn(new_build_orders.values(), "Linking"))
        self.links.update(dict(zip(new_build_orders.keys(), links)))

    def link(self, objects: List[StexObject]) -> StexObject:
        """ Links a list of objects in the order they are provided.

        The last object will be treated as the "entry point" and only that
        object will give it's non-build-list related information to the
        linked object.

        Paramters:
            objects: List of object to be linked.
        
        Returns:
            A new object with all the relevant information of all objects.
        """
        linked = StexObject(self.root)
        for object in objects:
            linked.link(object, object == objects[-1])
        return linked

    @staticmethod
    def _make_build_order(
        root: StexObject,
        module_index: Dict[Path, Dict[str, StexObject]],
        build_order_cache: Dict[StexObject, OrderedDict[StexObject, bool]] = None,
        import_location: Location = None,
        cycle_check: Dict[StexObject, Location] = None) -> OrderedDict[StexObject, bool]:
        """ Recursively creates the build order for a root object.

        Parameters:
            root: Root StexObject the build order will be created for.
            module_index: Index of file->module_name->module_object. Required for the dependencies each module has.
            build_order_cache: Dynamic programming cache which stores the build orders of already visited objects.
            import_location: Optional location the root object was imported from.
            cycle_check:
                A dictionary which stores objects and the location they were first imported.
                Used to detect cycles and raise an exception if one occurs.
        
        Returns:
            Ordered dictionary of objects in the build order and their export status.
            Objects listed last are dependent on the objects listed at the front.
        """
        cycle_check = dict() if cycle_check is None else cycle_check
        build_order_cache = dict() if build_order_cache is None else build_order_cache
        if root not in build_order_cache:
            build_order: OrderedDict[StexObject, bool] = OrderedDict()
            for module, files in root.dependencies.items():
                for path, locations in files.items():
                    if path not in module_index:
                        # for location in locations:
                        #     root.errors[location].append(LinkError(f'Imported file not found: "{path}"'))
                        continue
                    object = module_index[path].get(module)
                    if not object:
                        # for location in locations:
                        #     root.errors[location].append(LinkError(f'Module not found: "{module.identifier}"'))
                        continue
                    if len(locations) > 1:
                        l = list(locations)
                        for location in l[1:]:
                            root.errors[location].append(LinkWarning(f'Multiple imports of module "{module}", first imported in {l[0].range.start.format()}.'))
                    for location, (public, _) in locations.items():
                        if not public:
                            build_order[object] = public
                            continue
                        if object in cycle_check:
                            root.errors[location].append(LinkError(f'{location.format_link()}: Cyclic dependency "{module}" imported at "{cycle_check[object].format_link()}"'))
                            continue
                        child_cycle_check = cycle_check.copy() # copy to emulate depth first search
                        child_cycle_check[object] = location
                        child_build_order = Linker._make_build_order(
                            root=object,
                            module_index=module_index,
                            import_location=location,
                            build_order_cache=build_order_cache,
                            cycle_check=child_cycle_check)
                        if root in build_order_cache:
                            root.errors[location].append(LinkError(f'Invalid build order: "{root.path}" was built multiple times.'))
                        new_build_order = OrderedDict()
                        for child, exported in child_build_order.items():
                            if not exported:
                                continue
                            if child in build_order:
                                del build_order[child]
                            new_build_order[child] = public
                        new_build_order.update(build_order)
                        build_order = new_build_order
            build_order[root] = True
            build_order_cache[root] = build_order
        return build_order_cache[root]

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
