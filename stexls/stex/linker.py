""" This module contains the linker that links

The idea here is that it mirrors the "ln" command for c++.
The ln command takes a list of c++ objects and resolves the symbol references inside them.
"""
from pathlib import Path
from os import PathLike
from time import time
from typing import Dict, List, Optional, Tuple

from stexls.stex.compiler import (Compiler, Dependency,
                                  ObjectfileIsCorruptedError,
                                  ObjectfileNotFoundError, StexObject)
from stexls.stex import exceptions
from stexls.stex import symbols
from stexls import vscode

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

    def __init__(self, compiler_outdir: PathLike):
        # Directory in which the compiler stores the compiled objects
        self.outdir = Path(compiler_outdir)
        # Dict[usemodule_on_stack?, [File, [ModuleName, (TimeModified, StexObject)]]]
        # ModuleName is the name of the Module that is guaranteed to be fully linked inside StexObject
        self.cache: Dict[Optional[bool], Dict[Path, Dict[str, Tuple[float, StexObject]]]] = {
            True: dict(), False: dict()}

    def link_dependency(self, obj: StexObject, dependency: Dependency, imported: StexObject):
        ''' Links the module specified in @dependency from @imported with @obj at the scope declared in the
        dependency.

        The module and it's public child symbols will be copied into the scope specified in the dependency.

        Parameters:
            obj: Object that has the @dependency to @imported
            dependency: Dependency of the object @obj
            imported: The Object that contains the file and module specified in @dependency
        '''
        resolved = imported.symbol_table.lookup(dependency.module_name)
        if len(resolved) > 1:
            obj.diagnostics.unable_to_link_with_non_unique_module(
                dependency.range, dependency.module_name, imported.file)
            return
        if not resolved:
            obj.diagnostics.undefined_module_not_exported_by_file(
                dependency.range, dependency.module_name, imported.file)
            return
        for module in resolved:
            if module.access_modifier != symbols.AccessModifier.PUBLIC:
                obj.diagnostics.attempt_access_private_symbol(
                    dependency.range, dependency.module_name)
                continue
            try:
                dependency.scope.import_from(module)
            except (exceptions.InvalidSymbolRedifinitionException, exceptions.DuplicateSymbolDefinedError):
                # TODO: I'm not sure that this error here necessarily has a redundant import as consequence
                # TODO: Theres currently no way of finding out what imported the redundant module.
                obj.diagnostics.redundant_import_check(
                    dependency.range, dependency.module_name)

    def link(
            self,
            file: PathLike,
            objects: Dict[Path, StexObject],
            compiler: Compiler,
            required_symbol_names: List[str] = None,
            *,
            _stack: Dict[Tuple[Path, str],
                         Tuple[StexObject, Dependency]] = None,
            _toplevel_module: str = None,
            _usemodule_on_stack: bool = False) -> StexObject:
        # load the objectfile
        # The object must be loaded from file because a deep copy (especially of the dependencies) is required
        # load_from_objectfile can raise FileNotFound but this should have been caught even before attempting to link the object
        path = Path(file)
        obj = compiler.load_from_objectfile(path)
        obj.creation_time = time()
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
                cyclic_obj, cyclic_dep = _stack[(
                    dep.file_hint, dep.module_name)]
                cyclic_location = vscode.Location(path.as_uri(), dep.range)
                obj.diagnostics.cyclic_dependency(
                    cyclic_dep.range, cyclic_dep.module_name, cyclic_location)
                continue
            update_usemodule_on_stack = _usemodule_on_stack or not dep.export
            if dep.file_hint not in objects:
                obj.diagnostics.file_not_found(dep.range, dep.file_hint)
                continue
            if self._relink_required(objects, dep.file_hint, dep.module_name, update_usemodule_on_stack):
                # compile and link the dependency if the context is not on stack, the file is not index and the file requires recompilation
                _stack[(dep.file_hint, dep.module_name)] = (obj, dep)
                if _toplevel_module is None:
                    current_module = dep.scope.get_current_module()
                    assert current_module is not None, "Invalid state: If toplevel is not set, then the scope must have a module in scope."
                    _toplevel_module = current_module.name
                try:
                    imported = self.link(
                        objects=objects,
                        file=dep.file_hint,
                        compiler=compiler,
                        required_symbol_names=[dep.module_name],
                        _stack=_stack,
                        _toplevel_module=_toplevel_module,
                        _usemodule_on_stack=update_usemodule_on_stack)
                    self._store_linked(
                        update_usemodule_on_stack, dep.file_hint, dep.module_name, imported)
                except (ObjectfileNotFoundError, ObjectfileIsCorruptedError):
                    log.exception('Failed to link dependency: %s', path)
                    continue
                finally:
                    del _stack[(dep.file_hint, dep.module_name)]
            else:
                # If the linked file is already indexed for the current context, than load it
                _mtime, imported = self._load_linked(
                    update_usemodule_on_stack, dep.file_hint, dep.module_name)
                assert imported, "Invalid state: Cached file not found even though it should be present."
            # Link the single dependency to the current object
            self.link_dependency(obj, dep, imported)
        return obj

    def _relink_required(self, compiled_objects: Dict[Path, StexObject], file: Path, module_name: str, usemodule_on_stack: bool) -> bool:
        ' Returns True if the module in the file was not linked yet or if a newer version can be created. '
        mtime, obj = self._load_linked(usemodule_on_stack, file, module_name)
        if not obj:
            # Module not cached
            return True
        if file in compiled_objects and mtime < compiled_objects[file].creation_time:
            # The sourcefile has been recompiled for some reason
            return True
        try:
            # Check whether any file referenced by a dependency or symbol is newer than this link
            for path in set(obj.related_files):
                if path in compiled_objects and mtime < compiled_objects[path].creation_time:
                    # The object of a dependency has been recompiled
                    return True
            return False
        except Exception:
            log.exception('Failed relink check')
        return True

    def _load_linked(self, usemodule_on_stack: bool, file: Path, module: str) -> Tuple[float, StexObject]:
        ' Return the tuple of (timestamp added, stexobj) from cache or (None, None) if not cached. '
        linked = self.cache.get(
            usemodule_on_stack, {}
        ).get(
            str(file), {}
        ).get(module, (None, None))
        return linked

    def _store_linked(self, usemodule_on_stack: bool, file: Path, module: str, obj: StexObject):
        ' Store an obj in cache. '
        self.cache[usemodule_on_stack].setdefault(
            str(file), {})[module] = (time(), obj)

    def validate_object_references(self, linked: StexObject, more_objects: Dict[Path, StexObject] = None):
        ''' Validate the references inside an object.

        This step should be called a single time after an object was linked.

        Parameters:
            linked: The object that needs validation
            more_objects: Additional information about objects in the workspace
        '''
        # TODO: Use more_objects to create global reference suggestions and missing module imports
        # TODO: Problem: Need to be able to quickly find modules and symbol names and a faster method for searching than difflib.get_close_matches
        for ref in linked.references:
            refname = "?".join(ref.name)
            # TODO: Does using ref.reference_type to specify the expected type restrict too much?
            resolved: List[symbols.Symbol] = ref.scope.lookup(
                ref.name, ref.reference_type)
            if not resolved:
                similar_symbols = linked.find_similar_symbols(
                    ref.scope, ref.name, ref.reference_type)
                linked.diagnostics.undefined_symbol(
                    ref.range, refname, ref.reference_type, similar_symbols)
            for symbol in resolved:
                # TODO: Are these warnings really useful? (currently not matching symbols are filtered out during lookup)
                # Reasoning: It's okay to have e.g. modules and symbols of the same name so there may exist
                # symbols in the scope of the same name that just don't match and are not expected to match.
                #                 if symbol.reference_type not in ref.reference_type:
                #                     linked.diagnostics.referenced_symbol_type_check(ref.range, ref.reference_type, symbol.reference_type)
                #                 else:
                #                     # Only add to valid resolved symbols if the reference type matches
                #                     ref.resolved_symbols.append(symbol)
                ref.resolved_symbols.append(symbol)
                if isinstance(symbol, symbols.DefSymbol):
                    defs: symbols.DefSymbol = symbol
                    if defs.noverb:
                        linked.diagnostics.symbol_is_noverb_check(
                            ref.range, refname, related_symbol_location=symbol.location)
                    binding: symbols.BindingSymbol = defs.get_current_binding()
                    if binding and binding.lang in defs.noverbs:
                        linked.diagnostics.symbol_is_noverb_check(
                            ref.range, refname, binding.lang, related_symbol_location=symbol.location)
