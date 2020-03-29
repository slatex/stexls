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
        self.compiled_files: Set[Path] = set()
        self.dependend_files: Dict[Path, Set[Location]] = defaultdict(set)
        self.export: Dict[Path, Dict[Range, Set[Location]]] = defaultdict(dict)
        self.symbol_table: Dict[str, List[Symbol]] = defaultdict(list)
        self.references: Dict[Path, Dict[Range, str]] = defaultdict(dict)
        self.errors: Dict[Location, List[Exception]] = defaultdict(list)

    @property
    def path(self) -> Path:
        if len(self.compiled_files) > 1:
            raise ValueError('Path of origin of this StexObject not unique.')
        return next(iter(self.compiled_files), None)

    def resolve(self, id: str, unique: bool = True, must_resolve: bool = True) -> List[Symbol]:
        symbols = self.symbol_table.get(id, [])
        if unique and len(symbols) > 1:
            raise CompilerException(f'Multiple symbols with id "{id}" found: {symbols}')
        if must_resolve and not symbols:
            raise CompilerException(f'Unable to resolve id "{id}".')
        return symbols

    def format(self):
        formatted = 'Contains files:'
        for f in self.compiled_files:
            formatted += '\n\t' + str(f)

        formatted += '\n\nDepends on:'
        if not self.dependend_files:
            formatted += ' <no dependend files>'
        else:
            for f in self.dependend_files:
                formatted += '\n\t' + str(f)
        
        formatted += '\n\nSymbols:'
        if not self.symbol_table:
            formatted += ' <no symbols>'
        else:
            for id, ss in self.symbol_table.items():
                for s in ss:
                    formatted += '\n\t' + s.location.format_link() + ':' + str(s)

        formatted += '\n\nReferences:'
        if not self.references:
            formatted += ' <no references>'
        else:
            for path, d in self.references.items():
                for r, id in d.items():
                    formatted += '\n\t' + Location(path, r).format_link() + ':' + str(id)
        
        formatted += '\n\nErrors:'
        if not self.errors:
            formatted += ' <no errors>'
        else:
            for loc, ee in self.errors.items():
                for e in ee:
                    formatted += '\n\t' + loc.format_link() + ':' + str(e)
        
        return formatted
    
    def add_dependency(self, location: Location, file: Path, export: bool = False):
        self.dependend_files[file].add(location)
        if export:
            self.export[location.uri].setdefault(location.range, set()).add(file)
    
    def add_reference(self, location: Location, referenced_id: str):
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
        obj = StexObject()
        obj.errors = parsed.errors.copy()
        obj.compiled_files.add(parsed.path)
        number_of_roots = len(parsed.modnls) + len(parsed.modsigs) + len(parsed.modules)
        if number_of_roots == 0 and not parsed.errors:
            return
        if number_of_roots > 1:
            raise CompilerException(f'Too many stex roots found: Found {number_of_roots}, expected up to 1')
        for modsig in parsed.modsigs:
            _compile_modsig(modsig, obj, parsed)
        for modnl in parsed.modnls:
            _compile_modnl(modnl, obj, parsed)
        for module in parsed.modules:
            _compile_module(module, obj, parsed)
        return obj


def _map_compile(compile_fun, arr: List, obj: StexObject):
    for item in arr:
        try:
            compile_fun(item, obj)
        except CompilerException as e:
            obj.errors[item.location].append(e)

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
    obj.add_dependency(gimport.location, gimport.path, export=gimport.export)
    obj.add_reference(gimport.location, gimport.module.text)

def _compile_importmodules(module: ModuleSymbol, importmodule: ImportModule, obj: StexObject):
    obj.add_dependency(importmodule.location, importmodule.path, export=importmodule.export)
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
    module_id = SymbolIdentifier(modnl.name.text, SymbolType.MODULE)
    name_location = modnl.location.replace(positionOrRange=modnl.name.range)
    obj.add_reference(name_location, module_id.identifier)
    obj.add_dependency(name_location, modnl.path)
    for invalid_environment in itertools.chain(
        parsed_file.modsigs,
        parsed_file.modules,
        parsed_file.gimports,
        parsed_file.importmodules,
        parsed_file.symdefs,
        parsed_file.syms):
        obj.errors[invalid_environment.location].append(CompilerWarning(f'Invalid environment of type {type(invalid_environment).__name__} in modnl.'))
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
        module_location = trefi.location.replace(positionOrRange=trefi.module.range)
        obj.add_reference(module_location, module_id.identifier)
    target_symbol_id = module_id.append(SymbolIdentifier(trefi.name, SymbolType.SYMBOL))
    obj.add_reference(trefi.location, target_symbol_id.identifier)

def _compile_module(module: Module, obj: StexObject, parsed_file: ParsedFile):
    module_id = SymbolIdentifier(module.id.text, SymbolType.MODULE)
    name_location = module.location.replace(positionOrRange=module.id.range)
    obj.add_reference(name_location, module_id.identifier)
    for invalid_environment in itertools.chain(
        parsed_file.modsigs,
        parsed_file.modnls,
        parsed_file.gimports,
        parsed_file.importmodules,
        parsed_file.symdefs,
        parsed_file.syms):
        obj.errors[invalid_environment.location].append(CompilerWarning(f'Invalid environment of type {type(invalid_environment).__name__} in module.'))
    _map_compile(functools.partial(_compile_defi, module_id, create=True), parsed_file.defis, obj)
    _map_compile(functools.partial(_compile_trefi, module_id), parsed_file.trefis, obj)
