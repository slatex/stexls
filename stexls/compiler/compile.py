from __future__ import annotations
from typing import Dict, Optional, Set, Union
import itertools
from pathlib import Path
from collections import defaultdict
from stexls.util.location import *
from stexls.compiler.parse import *
from stexls.compiler.symbols import *

__all__ = ['StexObject']

class StexObject:
    def __init__(self):
        self.compiled_files: Set[Path] = set()
        self.dependend_files: Set[Path] = set()
        self.symbol_table: Dict[SymbolIdentifier, List[Symbol]] = defaultdict(list)
        self.references: Dict[Path, Dict[Range, SymbolIdentifier]] = defaultdict(dict)
        self.errors: Dict[Location, Exception] = {}
    
    def add_reference(self, location: Location, referenced_id: SymbolIdentifier):
        self.references[location.uri][location.range] = referenced_id

    def add_symbol(self, symbol: Symbol, export: bool = False, duplicate_allowed: bool = False):
        symbol.access_modifier = AccessModifier.PUBLIC if export else AccessModifier.PRIVATE
        if symbol.qualified_identifier in self.symbol_table:
            if duplicate_allowed:
                for duplicate in self.symbol_table[symbol.qualified_identifier]:
                    if duplicate.access_modifier != symbol.access_modifier:
                        raise ValueError(f'Duplicate symbol definition of {symbol.qualified_identifier} at "{symbol.location}" and "{duplicate.location}" where access modifiers are different: {symbol.access_modifier.name} vs. {duplicate.access_modifier.name}')
            else:
                raise ValueError(f'Duplicate symbol definition of {symbol.qualified_identifier}: Previously defined at "{self.symbol_table[symbol].location}"')
        self.symbol_table[symbol.qualified_identifier].append(symbol)

    @staticmethod
    def compile(parsed: ParsedFile) -> Optional[StexObject]:
        obj = StexObject()
        obj.compiled_files.add(parsed.path)
        if len(parsed.mhmodnls) > 1:
            raise ValueError(f'Too many language bindings in file: Found {len(parsed.mhmodnls)}')
        if len(parsed.modsigs) > 1:
            raise ValueError(f'Too many module signatures in file: Found {len(parsed.modsigs)}')
        number_of_roots = len(parsed.mhmodnls) + len(parsed.modsigs) 
        if number_of_roots == 0:
            return
        if number_of_roots > 1:
            raise ValueError(f'Mixing of module signature and binding not allowed.')
        for modsig in parsed.modsigs:
            _compile_modsig(modsig, obj, parsed)
        for mhmodnl in parsed.mhmodnls:
            _compile_mhmodnl(mhmodnl, obj, parsed)
        return obj


def _compile_modsig(modsig: Modsig, obj: StexObject, parsed_file: ParsedFile):
    module = ModuleSymbol(modsig.location, modsig.name.text)
    for invalid_environment in itertools.chain(
        parsed_file.mhmodnls,
        parsed_file.defis,
        parsed_file.trefis):
        obj.errors[invalid_environment.location] = Warning(f'Invalid environment of type {type(invalid_environment).__name__} in mhmodnl.')
    for gimport in parsed_file.gimports:
        _compile_gimport(module, gimport, obj)
    for sym in parsed_file.syms:
        _compile_sym(module, sym, obj)
    for symd in parsed_file.symdefs:
        _compile_symdef(module, symd, obj)

def _compile_gimport(module: ModuleSymbol, gimport: GImport, obj: StexObject):
    repository_path = gimport.repository_path_annotation
    module_path = gimport.module_path
    if repository_path:
        obj.dependend_files.add(module_path.absolute())
    target_module_placeholder = PlaceholderSymbol(
        gimport.target_module_name, module.qualified_identifier)
    referenced_module_id = SymbolIdentifier(gimport.target_module_name, SymbolType.MODULE)
    obj.add_reference(gimport.location, referenced_module_id)
    obj.add_symbol(target_module_placeholder, export=True)

def _compile_sym(module: ModuleSymbol, sym: Symi, obj: StexObject):
    symbol = DefSymbol(sym.location, sym.name, module.qualified_identifier)
    obj.add_symbol(symbol, export=True)

def _compile_symdef(module: ModuleSymbol, symdef: Symdef, obj: StexObject):
    symbol = DefSymbol(symdef.location, symdef.name, module.qualified_identifier)
    obj.add_symbol(symbol, duplicate_allowed=True, export=True)

def _compile_mhmodnl(mhmodnl: Mhmodnl, obj: StexObject, parsed_file: ParsedFile):
    module_id = SymbolIdentifier(mhmodnl.name.text, SymbolType.MODULE)
    binding = BindingSymbol(mhmodnl.location, lang=mhmodnl.lang.text, module=module_id)
    obj.add_dependency(mhmodnl.location, mhmodnl.path_to_module_file)
    obj.add_symbol(binding, export=True)
    for invalid_environment in itertools.chain(
        parsed_file.modsigs,
        parsed_file.gimports,
        parsed_file.symdefs,
        parsed_file.syms):
        obj.errors[invalid_environment.location] = Warning(f'Invalid environment of type {type(invalid_environment).__name__} in mhmodnl.')
    for defi in parsed_file.defis:
        try:
            _compile_defi(binding, defi, obj)
        except Exception as e:
            obj.errors[defi.location] = e
    for trefi in parsed_file.trefis:
        try:
            _compile_trefi(binding, trefi, obj)
        except Exception as e:
            obj.errors[trefi.location] = e

def _compile_defi(binding: BindingSymbol, defi: Defi, obj: StexObject):
    defi_id = SymbolIdentifier(defi.name, SymbolType.SYMBOL)
    symbol_id = binding.parent.append(defi_id)
    obj.add_reference(defi.location, symbol_id)

def _compile_trefi(binding: BindingSymbol, trefi: Trefi, obj: StexObject):
    target_module, _, module_range, symbol_range = trefi.parse_annotations()
    if target_module is None:
        module_id = binding.parent
    else:
        target_id = SymbolIdentifier(target_module, SymbolType.MODULE)
        module_id = binding.parent.append(target_id)
    symbol_id = module_id.append(SymbolIdentifier(trefi.target_symbol, SymbolType.SYMBOL))
    obj.add_reference(trefi.location, symbol_id)
    if module_range is not None:
        module_location = trefi.location.replace(positionOrRange=module_range)
        obj.add_reference(module_location, module_id)