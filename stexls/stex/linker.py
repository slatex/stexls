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
from stexls.stex.symbols import Symbol, SymbolIdentifier, VerbSymbol, ModuleSymbol, SymbolType
from .exceptions import *

import pkg_resources

__all__ = ['Linker']

import logging
log = logging.getLogger(__name__)

class Linker:
    def __init__(self, root: Path):
        self.root = Path(root).expanduser().resolve().absolute()
        # Keeps track of all objects currently used to create links
        self.objects: Dict[Path, List[StexObject]] = dict()
        # Keeps track of errors raised when making build orders
        # this is needed because these errors need to be added later to the link which currently doesnt exist
        self.errors: Dict[StexObject, Dict[Location, List[Exception]]] = dict()
        # Build orders for every object
        self.build_orders: Dict[StexObject, OrderedDict[StexObject, bool]] = dict()
        # The finished linked objects
        self.links: Dict[StexObject, StexObject] = dict()

    def _cleanup(self, files: Dict[Path, List[StexObject]]):
        """ This is an private method used to clean up old references to objects from files given in the keys() of the files dict.

            This method goes through the list of files and deletes errors, build orders and links
            related to these files. Also the list of root objects provided in the dict's values()
            are stored for later use.

        Parameters:
            files: Dictionary of paths to a list of toplevel objects they export.
        """
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
            if objects is None:
                if path in self.objects:
                    del self.objects[path]
            else:
                self.objects[path] = objects

    def link(
        self,
        inputs: Dict[Path, List[StexObject]],
        modules: Dict[Path, Dict[SymbolIdentifier, StexObject]],
        progressfn: Callable[[str], Callable[[Iterable], Iterable]] = None,
        use_multiprocessing: bool = True) -> Dict[StexObject, StexObject]:
        """ This is the main functionality of the linker. It links all the input files using the provided importable modules dictionary.

        Parameters:
            inputs: Map of all files with their objects which need to be linked.
            modules: A dictionary of files to the dictionary of module id's to the module objects they export.
        
        Keyword Parameters:
            progressfn: A progress function.
            use_multiprocessing: Enables multiprocessing.
        
        Returns:
            A linked object for all objects provided in files.
        """
        progressfn = progressfn or (lambda title: lambda it: it)
        self._cleanup(inputs)
        build_orders = self._resolve_dependencies(inputs, modules, progressfn('Resolving Dependencies'))
        links = self._link(build_orders, progressfn('Linking'), use_multiprocessing)
        self._validate_references(links)
        return links

    def _validate_references(self, links: Dict[StexObject, StexObject]):
        """ This method finds errors related to unreferenced symbols and referenced symbols that are marked as noverb. """
        unreferenced: Dict[Location, Dict[Symbol, StexObject]] = dict()
        referenced_locations: Set[Location] = set()
        for origin, link in links.items():
            language: Optional[str] = next(origin.language_bindings, None)
            for id, symbols in origin.symbol_table.items():
                if id.symbol_type == SymbolType.BINDING:
                    continue
                for symbol in symbols:
                    unreferenced.setdefault(symbol.location, dict())[symbol] = link
            for path, ranges in origin.references.items():
                for range, referenced_id in ranges.items():
                    if referenced_id.symbol_type == SymbolType.BINDING:
                        continue
                    for referenced_symbol in link.symbol_table.get(referenced_id, ()):
                        referenced_locations.add(referenced_symbol.location)
                        if isinstance(referenced_symbol, VerbSymbol):
                            referenced_symbol: VerbSymbol
                            # additionally if the reference is a verb check also that it is not marked noverb
                            if referenced_symbol.noverb:
                                reference_location = Location(path.as_uri(), range)
                                link.errors.setdefault(reference_location, []).append(
                                    LinkWarning(f'Referenced "noverb" symbol "{referenced_id.identifier}" defined at "{referenced_symbol.location.format_link()}"'))
                            # and that the language of the current origin is not listed in the noverb languages
                            if language in referenced_symbol.noverbs:
                                reference_location = Location(path.as_uri(), range)
                                link.errors.setdefault(reference_location, []).append(
                                    LinkWarning(f'Referenced symbol "{referenced_id.identifier}" is marked "noverb" for the language "{language}" at "{referenced_symbol.location.format_link()}"'))
        for ref, symbols in unreferenced.items():
            if ref not in referenced_locations:
                for symbol, link in symbols.items():
                    link.errors.setdefault(symbol.location, []).append(
                        LinkWarning(f'Symbol never referenced: {symbol.qualified_identifier.identifier}'))

    def relevant_objects(self, file: Path, line: int, column: int) -> Iterator[StexObject]:
        """ Determines the stex objects at the current coursor position. """
        for object in self.objects.get(file, ()):
            if object.module:
                for module in object.symbol_table.get(object.module, ()):
                    if module.full_range.contains(Position(line, column)):
                        if object in self.links:
                            yield self.links[object]
            elif object in self.links:
                yield self.links[object]

    def definitions(self, file: Path, line: int, column: int) -> List[Tuple[Range, Symbol]]:
        """ Finds definitions at the current cursor position.
        
        Returns:
            List of tuples with (the range used to create the link on mouse hover, The symbol found at the location)
        """
        definitions: Dict[int, List[Tuple[Range, Symbol]]] = {}
        position = Position(line, column)
        origin = Location(file.as_uri(), position)
        for object in self.relevant_objects(file, line, column):
            for id, symbols in object.symbol_table.items():
                for symbol in symbols:
                    if symbol.location.contains(origin):
                        range = symbol.location.range
                        definitions.setdefault(range.length, []).append((range, symbol))
            for range, id in object.references.get(file, {}).items():
                if range.contains(position):
                    for symbol in object.symbol_table.get(id, ()):
                        definitions.setdefault(range.length, []).append((range, symbol))
        if definitions:
            return definitions[min(definitions)]
        else:
            return []

    def references(self, symbol: Symbol) -> List[Location]:
        """ Finds all references to the specified symbol (only if the symbol is properly imported). """
        references = []
        for _, link in self.links.items():
            if symbol.location.path not in link.files:
                # ignore this link if the file of the symbol
                # is not even imported by the link
                continue
            for path, ranges in link.references.items():
                for range, id in ranges.items():
                    if symbol.qualified_identifier == id:
                        references.append(Location(path.as_uri(), range))
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

    def _resolve_dependencies(
        self,
        inputs: Dict[Path, List[StexObject]],
        modules: Dict[Path, Dict[SymbolIdentifier, StexObject]],
        progressfn: Callable[[Iterable], Iterable]) -> Dict[StexObject, List[StexObject]]:
        """ This is the resolve dependency step during linking.

        This step takes all the new objects and resolves their respective dependencies.
        Creating the order in which the imported module should be linked together in order
        to properly create a link for the input objects.

        Parameters:
            inputs:
                Map of files to the objects they export.
                The build orders will be created for each of these exported objects.
            modules:
                Map of files to a map of module symbol identifiers to the object containing
                the module. This map is used to efficiently find the dependencies.
            progressfn:
                Optional progress report function.

        Returns:
            Map of origin stex object to the list of objects their link needs to link against
            to be build properly.
        """
        build_orders: Dict[StexObject, List[StexObject]] = dict()
        for _, objects in progressfn(inputs.items()):
            for object in objects:
                self.errors[object] = {}
                build_orders[object] = Linker._make_build_order(object, modules, self.errors[object])
        self.build_orders.update(build_orders)
        return build_orders
    
    def _link(
        self,
        build_orders: Dict[StexObject, List[StexObject]],
        progressfn: Callable[[Iterable], Iterable],
        use_multiprocessing: bool = True) -> Dict[StexObject, StexObject]:
        """ This is the final link step.

            Takes map of origin objects and their respective build orders as input in 
            order to create the linked object.
        
        Parameters:
            build_orders: Map of objects to the build order they need to be linked against.
            progressfn: Optional progress report function.
            use_multiprocessing: Enables multiprocessing.
        
        Returns:
            Map of origin objects to the new linked object.
        """
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

    @staticmethod
    def _make_build_order(
        current: StexObject,
        modules: Dict[Path, Dict[SymbolIdentifier, StexObject]],
        errors: Dict[Location, List[Exception]],
        build_order_cache: Dict[StexObject, List[StexObject]] = None,
        cyclic_stack: OrderedDict[StexObject, Location] = None,
        at_toplevel: bool = True,
        usemodule_on_stack: bool = False,
        root: StexObject = None) -> List[StexObject]:
        """ Recursively creates the build order for a root object.

            It takes a current object, a dictionary of modules that can be imported and
            a output dictionary for the errors that are relevant to the first "current" object provided.
            All the keyword arguments are internal and not to be used by the user who wants to create a
            build order for the current object.

        Parameters:
            current:
                The current object for which the build order is being generated.
            modules:
                A dictionary of (filepath)->(module identifier)->(object with that module).
                The Path is the path to the file which contains the module with the SymbolIdentifier.
                And the object is the object which contains the mdoule with the specified SymbolIdentifier.
                E.g.: modules[primenumber.tex][primenumber/MODULE] = compile(primenumber.tex)
            errors:
                An output dictionary which is used to store exceptions that occured during linking.
                Only errors which are relevant to the first "current" object will be added.

        Keyword Arguments:
            build_order_cache:
                A dictionary which maps source objects to their already computed build lists.
                Build orders can't be shared because they depend on the path they were imported on.
                It is used during the current linking processes in cases like
                A imports B and C, but B and C both import D. Then D only has to be computed once instead of twice.
            cyclic_stack:
                A dict of objects and the location they are imported from. Used to diagnose cyclic imports.
            at_toplevel:
                This should be used to indicate the "first current" object. This is required because
                only the toplevel current object can utilize "use" imports. This option must be false
                for all recursive usages.
            usemodule_on_stack:
                A simple flag which tracks whether a "usemodule" or "guse" type of import
                was used. If this is true, then we can ignore cyclic imports of the root object.
            root:
                This must be None for the toplevel. This is used to keep track of what the "first current"
                object was in recursive calls.

        Returns:
            Build order of the current object.
            Furthermore, errors related to the root object are stored in errors.
        """

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

