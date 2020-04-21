from typing import List, Dict, Tuple, Set, Iterator, Optional, OrderedDict, Pattern, Iterable, Iterator, Callable
from pathlib import Path
import os, functools
import multiprocessing
import difflib
import pickle
import functools
from hashlib import sha1
from stexls.util.vscode import *
from stexls.stex.parser import ParsedFile
from stexls.stex.compiler import StexObject
from stexls.stex.symbols import Symbol, SymbolIdentifier
from .exceptions import *

import pkg_resources

__all__ = ['Linker']

import logging
log = logging.getLogger(__name__)

class Linker:
    def __init__(self, root: Path):
        self.root = Path(root).expanduser().resolve().absolute()
        self.objects: Dict[Path, List[StexObject]] = dict()
        self.errors: Dict[StexObject, Dict[Location, List[Exception]]] = dict()
        self.build_orders: Dict[StexObject, OrderedDict[StexObject, bool]] = dict()
        self.links: Dict[StexObject, StexObject] = dict()

    def relevant_objects(self, file: Path, line: int, column: int) -> Iterator[StexObject]:
        for object in self.objects.get(file, ()):
            if object.module:
                for module in object.symbol_table.get(object.module, ()):
                    if module.full_range.contains(Position(line, column)):
                        if object in self.links:
                            yield self.links[object]
            elif object in self.links:
                yield self.links[object]

    def definitions(self, file: Path, line: int, column: int) -> List[Tuple[Range, Symbol]]:
        definitions = []
        position = Position(line, column)
        origin = Location(file.as_uri(), position)
        log.debug('Definitions at %s', origin.format_link())
        for object in self.relevant_objects(file, line, column):
            for id, symbols in object.symbol_table.items():
                for symbol in symbols:
                    log.debug('Compare to symbol %s at %s. Contained? %s', id, symbol.location.format_link(), symbol.location.contains(origin))
                    if symbol.location.contains(origin):
                        definitions.append((symbol.location.range, symbol))
            for range, id in object.references.get(file, {}).items():
                target = Location(file.as_uri(), range)
                log.debug('Compare to reference %s at %s. Contained? %s', id, target.format_link(), target.contains(origin))
                if target.contains(origin):
                    for symbol in object.symbol_table.get(id, ()):
                        definitions.append((range, symbol))
        return definitions

    def references(self, symbol: Symbol) -> List[Location]:
        references = []
        for path, objects in self.objects.items():
            for object in objects:
                for range, id in object.references.get(symbol.location.path, {}).items():
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

    def _resolve_dependencies(
        self,
        inputs: Dict[Path, List[StexObject]],
        modules: Dict[Path, Dict[SymbolIdentifier, StexObject]],
        progressfn: Callable[[Iterable], Iterable]) -> Dict[Path, List[StexObject]]:
        build_orders: Dict[StexObject, List[StexObject]] = dict()
        for _, objects in progressfn(inputs.items()):
            for object in objects:
                errors = {}
                build_orders[object] = Linker._make_build_order(object, modules, errors)
                self.errors[object] = errors
        self.build_orders.update(build_orders)
        return build_orders
    
    def _link(
        self,
        build_orders: Dict[StexObject, List[StexObject]],
        progressfn: Callable[[Iterable], Iterable],
        use_multiprocessing: bool = True) -> Dict[StexObject, StexObject]:
        linkfn = functools.partial(StexObject.link_list, root=self.root)
        with multiprocessing.Pool() as pool:
            mapfn = pool.map if use_multiprocessing else map
            futures = mapfn(linkfn, progressfn(build_orders.values()))
            links: Dict[StexObject, StexObject] = dict(zip(build_orders, futures))
            for obj, link in links.items():
                for loc, errors in self.errors.get(obj, {}).items():
                    link.errors.setdefault(loc, []).extend(errors)
        self.links.update(links)
        return links

    def _cleanup(self, files: Dict[Path, List[StexObject]]):
        ' Delete old objects related to the new files. '
        for path, objects in files.items():
            # delete old objects, build orders, errors and links related to
            # the new file
            if path in self.objects:
                for object in self.objects[path]:
                    if object in self.build_orders:
                        del self.build_orders[object]
                    if object in self.errors:
                        del self.errors[object]
                    if object in self.links:
                        del self.links[object]
            # add the objects from the new file again
            self.objects[path] = objects

    def link(
        self,
        inputs: Dict[Path, List[StexObject]],
        modules: Dict[Path, Dict[SymbolIdentifier, StexObject]],
        progressfn: Callable[[str], Callable[[Iterable], Iterable]] = None,
        use_multiprocessing: bool = True) -> Dict[StexObject, StexObject]:
        progressfn = progressfn or (lambda title: lambda it: it)
        self._cleanup(inputs)
        build_orders = self._resolve_dependencies(inputs, modules, progressfn('Resolving Dependencies'))
        links = self._link(build_orders, progressfn('Linking'), use_multiprocessing)
        return links

    @staticmethod
    def _make_build_order(
        current: StexObject,
        modules: Dict[Path, Dict[SymbolIdentifier, StexObject]],
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
                    if path not in modules:
                        if at_toplevel:
                            e = LinkError(f'Not a file: "{path}" does not exist or does not export any modules.')
                            for location in locations:
                                errors.setdefault(location, []).append(e)
                        continue

                    if module not in modules[path]:
                        if at_toplevel:
                            e = LinkError(f'Imported module not exported: "{module.identifier}" is not exported by "{path}"')
                            for location in locations:
                                errors.setdefault(location, []).append(e)
                        continue

                    object = modules[path][module]

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
                                errors.setdefault(cycle_start, []).append(
                                    LinkError(f'Cyclic dependency: Import of "{cycle_module.module.identifier}" creates cycle at "{cycle_end.format_link()}"'))
                            # always ignore this import to prevent infinite loops
                            continue

                        # Stack the child at the current location and compute it's build order
                        cyclic_stack[object] = location
                        child_build_order: List[StexObject] = Linker._make_build_order(
                            current=object, # next object
                            modules=modules, # inherit
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

