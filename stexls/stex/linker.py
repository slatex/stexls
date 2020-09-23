""" This module contains the linker that links 

The idea here is that it mirrors the "ln" command for c++.
The ln command takes a list of c++ objects and resolves the symbol references inside them.
"""
from typing import List, Dict, Tuple, Set, Iterator, Optional
from pathlib import Path
from stexls.vscode import *
from stexls.stex.compiler import StexObject, Compiler, Dependency, Reference, ReferenceType
from stexls.stex.symbols import *
from stexls.stex.exceptions import *
from stexls.stex import util
from stexls.util.format import format_enumeration
from stexls.util.workspace import Workspace
from time import time

__all__ = ['Linker']

import logging
log = logging.getLogger(__name__)

class Linker:
    """
    This linker does the same thing as the "ln", except that the name of the object file is inferred from the name of
    the sourcefile and the dependent objectfiles are also inferred from the dependencies inside the
    objects.

    A "ln dep1.o dep2.o main.o -o a.out" command is the same as "aout = Linker(...).link(main.tex)"
    Notice the main.o and main.tex inputs respectively.
    """
    def __init__(self, workspace: Workspace, compiler_outdir: Path):
        # TODO: Remove workspace dependency: The linker should not be responsible for checking updates
        # Workspace required for time modified checking for files
        self.workspace = workspace
        # Directory in which the compiler stores the compiled objects
        self.outdir = compiler_outdir
        # Dict[usemodule_on_stack?, [File, [ModuleName, (TimeModified, StexObject)]]]
        # ModuleName is the name of the Module that is guaranteed to be fully linked inside StexObject
        self.cache: Dict[Optional[bool], Dict[Path, Dict[str, Tuple[float, StexObject]]]] = {True: dict(), False: dict()}

    def link_dependency(self, obj: StexObject, dependency: Dependency, imported: StexObject):
        ' Links <imported> to <obj> at the scope specified in <dependency> '
        alts = imported.symbol_table.lookup(dependency.module_name)
        if len(alts) > 1:
            obj.errors.setdefault(dependency.range, []).append(
                LinkError(f'Module "{dependency.module_name}" not unique in "{imported.file}".'))
            return
        if not alts:
            obj.errors.setdefault(dependency.range, []).append(
                LinkError(f'Module "{dependency.module_name}" not defined in file "{imported.file}".'))
            return
        for module in alts:
            if module.access_modifier != AccessModifier.PUBLIC:
                obj.errors.setdefault(dependency.range, []).append(
                    LinkError(f'Module "{dependency.module_name}" can\'t be imported because it is marked private.'))
                return
            # TODO: Maybe let import_from raise all it's exception, then capture them here, add them to the obj for display
            dependency.scope.import_from(module)

    def link(
        self,
        file: Path,
        required_symbol_names: List[str] = None,
        _stack: Dict[Tuple[Path, str], Tuple[StexObject, Dependency]] = None,
        _toplevel_module: str = None,
        _usemodule_on_stack: bool = False) -> StexObject:
        # load the objectfile
        obj = Compiler.load_from_objectfile(self.outdir, file)
        if not obj:
            raise NotCompiledError(f'Sourcefile is not compiled and no objectfile was found: "{file}"')
        # initialize the stack if not already initialized
        _stack = {} if _stack is None else _stack
        # Cache initialization is a little bit more complicated
        for dep in obj.dependencies:
            if required_symbol_names and dep.scope.name not in required_symbol_names:
                continue
            if not dep.export and _stack:
                # TODO: Is this really how usemodules behave?
                # Skip usemodule dependencies if dep is not exportet and the stack is not empty, indicating
                # that this object is currently being imported
                continue
            if _usemodule_on_stack and dep.module_name == _toplevel_module:
                # TODO: Is this really how usemodules behave?
                # Ignore the import of the same module as the toplevel module if a usemodule import is
                # currently in the stack somewhere
                continue
            if (dep.file_hint, dep.module_name) in _stack:
                # if same current context of file_hint and module_name is on stack, a cyclic dependency occurs
                cyclic_obj, cyclic_dep = _stack[(dep.file_hint, dep.module_name)]
                cyclic_obj.errors.setdefault(cyclic_dep.range, []).append(
                    LinkError(
                        f'Dependency to module "{cyclic_dep.module_name}"'
                        f' creates cycle at "{Location(file.as_uri(), dep.range).format_link()}"'))
                continue
            update_usemodule_on_stack = _usemodule_on_stack or not dep.export
            if self._relink_required(dep.file_hint, dep.module_name, update_usemodule_on_stack):
                # compile and link the dependency if the context is not on stack, the file is not index and the file requires recompilation
                _stack[(dep.file_hint, dep.module_name)] = (obj, dep)
                try:
                    imported = self.link(
                        file=dep.file_hint,
                        required_symbol_names=[dep.module_name],
                        _stack=_stack,
                        _toplevel_module=_toplevel_module or dep.scope.get_current_module(),
                        _usemodule_on_stack=update_usemodule_on_stack)
                    self._store_linked(update_usemodule_on_stack, dep.file_hint, dep.module_name, imported)
                except Exception as err:
                    obj.errors.setdefault(dep.range, []).append(err)
                    continue
                finally:
                    del _stack[(dep.file_hint, dep.module_name)]
            else:
                # If the linked file is already indexed for the current context, than load it
                _mtime, imported = self._load_linked(update_usemodule_on_stack, dep.file_hint, dep.module_name)
                assert imported, "Invalid state: Cached file not found even though it should be present."
            # Link the single dependency to the current object
            self.link_dependency(obj, dep, imported)
        # Validate some stuff about the object after all dependencies have been linked.
        self.validate_linked_object(obj)
        return obj

    def _relink_required(self, file: Path, module_name: str, usemodule_on_stack: bool) -> bool:
        ' Returns True if the module in the file was not linked yet or if a newer version can be created. '
        # TODO: Integration of workspace.is_open and file time modified check can be done better maybe
        mtime, obj = self._load_linked(usemodule_on_stack, file, module_name)
        if not obj:
            # Module not cached
            return True
        if mtime < file.lstat().st_mtime or mtime < self.workspace.get_time_live_modified(file):
            # The sourcefile of the module has been update
            # Or the sourcefile is currently open and has received live upates
            # Check in case the sourcefile was empty previously and didnt have any symbols or dependencies
            return True
        try:
            # Check whether any file referenced by a dependency or symbol is newer than this link
            paths = set(symbol.location.path for symbol in obj.symbol_table)
            paths |= set(dep.file_hint for dep in obj.dependencies)
            for path in paths:
                if (path.is_file() and mtime < path.lstat().st_mtime) or mtime < self.workspace.get_time_live_modified(path):
                    return True
            return False
        except:
            log.exception('Failed relink check')
        return True

    def _load_linked(self, usemodule_on_stack: bool, file: Path, module: str) -> Tuple[float, StexObject]:
        ' Return the tuple of (timestamp added, stexobj) from cache or (None, None) if not cached. '
        return self.cache.get(usemodule_on_stack, {}).get(str(file), {}).get(module, (None, None))

    def _store_linked(self, usemodule_on_stack: bool, file: Path, module: str, obj: StexObject):
        ' Store an obj in cache. '
        self.cache[usemodule_on_stack].setdefault(str(file), {})[module] = (time(), obj)

    def validate_linked_object(self, linked: StexObject):
        for ref in linked.references:
            # TODO: Prevent validating references of modules that are not compiled yet? Use link(required_module)?
            refname = "?".join(ref.name)
            try:
                resolved: List[Symbol] = ref.scope.lookup(ref.name)
                if not resolved:
                    suggestions = format_enumeration(linked.find_similar_symbols(ref.name, ref.reference_type, ref.scope), last='or')
                    if suggestions:
                        err = LinkError(f'Undefined symbol "{refname}" of type {ref.reference_type.format_enum()}: '
                            f'Did you maybe mean {suggestions}?')
                    else:
                        err = LinkError(f'Undefined symbol "{refname}" of type {ref.reference_type.format_enum()}')
                    linked.errors.setdefault(ref.range, []).append(err)
            except ValueError:
                resolved = []
                linked.errors.setdefault(ref.range, []).append(
                    LinkError(f'Invalid reference to non-unique symbol "{refname}" of type {ref.reference_type.format_enum()}'))
            for symbol in resolved:
                if isinstance(symbol, DefType):
                    if ReferenceType.DEF not in ref.reference_type:
                        linked.errors.setdefault(ref.range, []).append(
                            LinkError(
                                f'Referenced verb "{refname}" wrong type:'
                                f' Found {ref.reference_type.format_enum()}, expected {ReferenceType.DEF.format_enum()}'))
                    defs: DefSymbol = symbol
                    if defs.noverb:
                        linked.errors.setdefault(ref.range, []).append(
                            LinkWarning(f'Referenced DefSymbol "{refname}" is marked as "noverb".'))
                    binding: BindingSymbol = defs.get_current_binding()
                    if binding and binding.lang in defs.noverbs:
                        linked.errors.setdefault(ref.range, []).append(
                            LinkWarning(
                                f'Referenced symbol "{refname}" is marked as "noverb"'
                                f' for the language {binding.lang}.'))
                elif isinstance(symbol, ModuleSymbol):
                    module: ModuleSymbol = symbol
                    if module.module_type == ModuleType.MODSIG and ReferenceType.MODSIG not in ref.reference_type:
                        linked.errors.setdefault(ref.range, []).append(
                            LinkError(f'Referenced modsig "{refname}" wrong type: Expected {ref.reference_type.format_enum()}'))
                    elif module.module_type == ModuleType.MODULE and ReferenceType.MODULE not in ref.reference_type:
                        linked.errors.setdefault(ref.range, []).append(
                            LinkError(f'Referenced module "{refname}" wrong type: Expected {ref.reference_type.format_enum()}'))
                elif isinstance(symbol, BindingSymbol):
                    binding: BindingSymbol = symbol
                    if ReferenceType.BINDING not in ref.reference_type:
                        linked.errors.setdefault(ref.range, []).append(
                            LinkError(f'Referenced symbol "{refname}" of wrong type: Expected "binding", found {ref.reference_type.format_enum()}'))

    def definitions(self, file: Path, line: int, column: int) -> List[Tuple[Range, Symbol]]:
        """ Finds definitions at the current cursor position.

        Returns:
            List of tuples with (the range used to create the link on mouse hover, The symbol found at the location)
        """
        # TODO

    def references(self, symbol: Symbol) -> List[Location]:
        """ Finds all references to the specified symbol (only if the symbol is properly imported). """
        # TODO

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
                for module in o.dependencies:
                    edges.setdefault(origin, set()).add(module.identifier)
        if not found:
            raise ValueError('No object found.')
        for origin, targets in edges.items():
            for target in targets:
                G.edge(origin, target)
        G.view(directory='/tmp/stexls')

