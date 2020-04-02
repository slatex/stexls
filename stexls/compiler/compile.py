from __future__ import annotations
from typing import Dict, Optional, Set, Union
import itertools, functools
from pathlib import Path
from collections import defaultdict
from stexls.util.location import *
from stexls.compiler.parse import *
from stexls.compiler.symbols import *
from stexls.compiler.exceptions import CompilerException, CompilerWarning

__all__ = ['StexObject']

class StexObject:
    def __init__(self):
        # Set of files used to compile this object
        self.files: Set[Path] = set()
        # Dependent module <str> from path hint <Path> referenced at set of locations <Location> and an export flag <bool>
        self.dependencies: Dict[Path, Dict[str, Set[Tuple[Location, bool]]]] = defaultdict(dict)
        # Symbol table with definitions: Key is symbol name for easy search access by symbol name
        self.symbol_table: Dict[str, List[Symbol]] = defaultdict(list)
        # Referenced symbol <str> in file <Path> at written in range <Range>
        self.references: Dict[Path, Dict[Range, str]] = defaultdict(dict)
        # Dict of list of errors generated at specific location
        self.errors: Dict[Location, List[Exception]] = defaultdict(list)

    @property
    def path(self) -> Path:
        if len(self.files) > 1:
            raise ValueError('Path of origin of this StexObject not unique.')
        return next(iter(self.files), None)

    def resolve(self, id: str, unique: bool = True, must_resolve: bool = True) -> List[Symbol]:
        symbols = self.symbol_table.get(id, [])
        if unique and len(symbols) > 1:
            raise CompilerException(f'Multiple symbols with id "{id}" found: {symbols}')
        if must_resolve and not symbols:
            raise CompilerException(f'Unable to resolve id "{id}".')
        return symbols

    def format(self):
        formatted = 'Contains files:'
        for f in self.files:
            formatted += '\n\t' + str(f)

        formatted += '\n\nDepends on:'
        if not self.dependencies:
            formatted += ' <no dependencies>'
        else:
            for filename, modules in self.dependencies.items():
                for module, locations in modules.items():
                    for location, export in locations:
                        public = 'public' if export else 'private'
                        formatted += f'\n\t{location.format_link()}:{public} {module} from "{filename}"'
        
        formatted += '\n\nSymbols:'
        if not self.symbol_table:
            formatted += ' <no symbols>'
        else:
            for id, symbols in self.symbol_table.items():
                for symbol in symbols:
                    formatted += f'\n\t{symbol.location.format_link()}:{symbol}'

        formatted += '\n\nReferences:'
        if not self.references:
            formatted += ' <no references>'
        else:
            for path, ranges in self.references.items():
                for range, id in ranges.items():
                    location = Location(path, range)
                    formatted += f'\n\t{location.format_link()}:{id}'
        
        formatted += '\n\nErrors:'
        if not self.errors:
            formatted += ' <no errors>'
        else:
            for location, errors in self.errors.items():
                for error in errors:
                    formatted += f'\n\t{location.format_link()}:{error}'
        
        return formatted
    
    def add_dependency(self, location: Location, file: Path, module_name: str, export: bool = False):
        """ Adds a dependency to a imported module in another file.

        Parameters:
            location: Location of where this dependency is created.
            file: Path to file that is referenced in the dependency.
            module_name: Module to import from that file.
            export: Export the imported symbols again.
        """
        self.dependencies[file].setdefault(module_name, set()).add((location, export))

    def add_reference(self, location: Location, referenced_id: str):
        """ Adds a reference.

        Parameters:
            location: Location of the string that creates this reference
            referenced_id: The id of the referenced symbol.
        """
        self.references[location.uri][location.range] = referenced_id

    def add_symbol(self, symbol: Symbol, export: bool = False, duplicate_allowed: bool = False):
        symbol.access_modifier = AccessModifier.PUBLIC if export else AccessModifier.PRIVATE
        if symbol.qualified_identifier.identifier in self.symbol_table:
            for duplicate in self.symbol_table.get(symbol.qualified_identifier.identifier, None):
                if duplicate.access_modifier != symbol.access_modifier:
                    raise CompilerException(
                        f'Duplicate symbol definition of {symbol.qualified_identifier}'
                        f' at "{symbol.location}" and "{duplicate.location}"'
                        f' where access modifiers are different:'
                        f' {symbol.access_modifier.name} vs. {duplicate.access_modifier.name}')
        self.symbol_table[symbol.qualified_identifier.identifier].append(symbol)

    @staticmethod
    def compile(parsed: ParsedFile) -> Optional[StexObject]:
        def _create(errors):
            obj = StexObject()
            obj.files.add(parsed.path)
            if errors:
                obj.errors = errors.copy()
            return obj
        number_of_roots = len(parsed.modnls) + len(parsed.modsigs) + int(len(parsed.modules) > 0)
        if number_of_roots > 1:
            obj = _create(parsed.errors)
            for env in itertools.chain(parsed.modnls, parsed.modsigs, parsed.modules):
                obj.errors[env.location].append(
                    CompilerException(f'Too many types of roots found: Found {number_of_roots}, expected up to 1'))
            if obj.errors or obj.references or obj.symbol_table:
                yield obj
        else: 
            toplevels = list(parsed)
            if toplevels:
                for toplevel in toplevels:
                    for modsig in toplevel.modsigs:
                        obj = _create(toplevel.errors)
                        _compile_modsig(modsig, obj, toplevel)
                        yield obj
                    for modnl in toplevel.modnls:
                        obj = _create(toplevel.errors)
                        _compile_modnl(modnl, obj, toplevel)
                        yield obj
                    for module in toplevel.modules:
                        obj = _create(toplevel.errors)
                        _compile_module(module, obj, toplevel)
                        yield obj
            else:
                obj = _create(parsed.errors)
                _compile_free(obj, parsed)
                if obj.errors or obj.references or obj.symbol_table:
                    yield obj


def _map_compile(compile_fun, arr: List, obj: StexObject):
    for item in arr:
        try:
            compile_fun(item, obj)
        except CompilerException as e:
            obj.errors[item.location].append(e)

def _compile_free(obj: StexObject, parsed_file: ParsedFile):
    _report_invalid_environments('file', parsed_file.modnls, obj)
    _report_invalid_environments('file', parsed_file.modules, obj)
    _report_invalid_environments('file', parsed_file.defis, obj)
    _report_invalid_environments('file', parsed_file.symdefs, obj)
    _report_invalid_environments('file', parsed_file.syms, obj)
    _report_invalid_environments('file', parsed_file.gimports, obj)
    _map_compile(functools.partial(_compile_importmodules, None), parsed_file.importmodules, obj)
    _map_compile(functools.partial(_compile_trefi, None), parsed_file.trefis, obj)

def _compile_modsig(modsig: Modsig, obj: StexObject, parsed_file: ParsedFile):
    for invalid_environment in itertools.chain(
        parsed_file.modnls,
        parsed_file.modules,
        parsed_file.defis,
        parsed_file.trefis):
        obj.errors[invalid_environment.location].append(CompilerWarning(f'Invalid environment of type {type(invalid_environment).__name__} in mhmodnl.'))
    module = ModuleSymbol(modsig.location, modsig.name.text)
    if parsed_file.path.name != f'{modsig.name.text}.tex':
        obj.errors[modsig.location].append(CompilerWarning(f'Invalid modsig filename: Expected "{modsig.name.text}.tex"'))
    obj.add_symbol(module, export=True)
    _map_compile(functools.partial(_compile_gimport, module), parsed_file.gimports, obj)
    _map_compile(functools.partial(_compile_importmodules, module), parsed_file.importmodules, obj)
    _map_compile(functools.partial(_compile_sym, module), parsed_file.syms, obj)
    _map_compile(functools.partial(_compile_symdef, module), parsed_file.symdefs, obj)

def _compile_gimport(module: ModuleSymbol, gimport: GImport, obj: StexObject):
    obj.add_dependency(gimport.location, gimport.path_to_imported_file, gimport.module.text.strip(), export=gimport.export)
    obj.add_reference(gimport.location, gimport.module.text)

def _compile_importmodules(module: ModuleSymbol, importmodule: ImportModule, obj: StexObject):
    obj.add_dependency(importmodule.location, importmodule.path_to_imported_file, importmodule.module.text.strip(), export=importmodule.export)
    obj.add_reference(importmodule.location, importmodule.module.text)

def _compile_sym(module: ModuleSymbol, sym: Symi, obj: StexObject):
    symbol = DefSymbol(
        location=sym.location,
        name=sym.name,
        module=module.qualified_identifier,
        noverb=sym.noverb.is_all,
        noverbs=sym.noverb.langs)
    obj.add_symbol(symbol, export=True)

def _compile_symdef(module: ModuleSymbol, symdef: Symdef, obj: StexObject):
    symbol = DefSymbol(
        location=symdef.location,
        name=symdef.name.text,
        module=module.qualified_identifier,
        noverb=symdef.noverb.is_all,
        noverbs=symdef.noverb.langs)
    obj.add_symbol(symbol, duplicate_allowed=True, export=True)

def _compile_modnl(modnl: Modnl, obj: StexObject, parsed_file: ParsedFile):
    if parsed_file.path.name != f'{modnl.name.text}.{modnl.lang.text}.tex':
        obj.errors[modnl.location].append(CompilerWarning(f'Invalid modnl filename: Expected "{modnl.name.text}.{modnl.lang.text}.tex"'))
    for invalid_environment in itertools.chain(
        parsed_file.modsigs,
        parsed_file.modules,
        parsed_file.gimports,
        parsed_file.importmodules,
        parsed_file.symdefs,
        parsed_file.syms):
        obj.errors[invalid_environment.location].append(CompilerWarning(f'Invalid environment of type {type(invalid_environment).__name__} in modnl.'))
    module_id = SymbolIdentifier(modnl.name.text, SymbolType.MODULE)
    name_location = modnl.location.replace(positionOrRange=modnl.name.range)
    obj.add_reference(name_location, module_id.identifier)
    obj.add_dependency(name_location, modnl.path, modnl.name.text)
    _map_compile(functools.partial(_compile_defi, module_id), parsed_file.defis, obj)
    _map_compile(functools.partial(_compile_trefi, module_id), parsed_file.trefis, obj)

def _compile_defi(module: SymbolIdentifier, defi: Defi, obj: StexObject, create: bool = False):
    if create:
        symbol = DefSymbol(defi.location, defi.name, module)
        obj.add_symbol(symbol, export=True)
    else:
        defi_id = SymbolIdentifier(defi.name, SymbolType.SYMBOL)
        symbol_id = module.append(defi_id)
        obj.add_reference(defi.location, symbol_id.identifier)

def _compile_trefi(module_id: SymbolIdentifier, trefi: Trefi, obj: StexObject):
    if trefi.module:
        module_id = SymbolIdentifier(trefi.module.text, SymbolType.MODULE)
        reference_location = trefi.location.replace(positionOrRange=trefi.module.range)
        obj.add_reference(reference_location, module_id.identifier)
    elif module_id is None:
        raise CompilerException('Invalid trefi configuration: Missing parent module name')
    target_symbol_id = module_id.append(SymbolIdentifier(trefi.name, SymbolType.SYMBOL))
    obj.add_reference(trefi.location, target_symbol_id.identifier)

def _compile_module(module: Module, obj: StexObject, parsed_file: ParsedFile):
    _report_invalid_environments('module', itertools.chain(parsed_file.modsigs, parsed_file.modnls, parsed_file.syms), obj)
    if module.id:
        name_location = module.location.replace(positionOrRange=module.id.range)
        module = ModuleSymbol(name_location, module.id.text)
        obj.add_symbol(module, export=True)
        _map_compile(functools.partial(_compile_importmodules, module), parsed_file.importmodules, obj)
        _map_compile(functools.partial(_compile_gimport, module), parsed_file.gimports, obj)
        _map_compile(functools.partial(_compile_symdef, module), parsed_file.symdefs, obj)
        _map_compile(functools.partial(_compile_defi, module.qualified_identifier, create=True), parsed_file.defis, obj)
        _map_compile(functools.partial(_compile_trefi, module.qualified_identifier), parsed_file.trefis, obj)
    else:
        _report_invalid_environments('module', itertools.chain(parsed_file.symdefs, parsed_file.defis), obj)
        _map_compile(functools.partial(_compile_importmodules, module), parsed_file.importmodules, obj)
        _map_compile(functools.partial(_compile_gimport, module), parsed_file.gimports, obj)
        _map_compile(functools.partial(_compile_trefi, None), parsed_file.trefis, obj)

def _report_invalid_environments(env_name: str, lst: List[ParsedEnvironment], obj: StexObject):
    for invalid_environment in lst:
        obj.errors[invalid_environment.location].append(
            CompilerWarning(f'Invalid environment of type {type(invalid_environment).__name__} in {env_name}.'))
