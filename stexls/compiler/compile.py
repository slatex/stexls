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
        self.symbol_table: Dict[SymbolIdentifier, Symbol] = {}
        self.references: Dict[Path, Dict[Range, SymbolIdentifier]] = defaultdict(dict)
        self.errors: Dict[Location, Exception] = {}

    def add_symbol(self, symbol: Symbol, duplicate_allowed: bool = False) -> Optional[Symbol]:
        if symbol in self.symbol_table:
            if duplicate_allowed:
                return self.symbol_table[symbol]
            raise ValueError(f'Duplicate symbol definition of {symbol}: Previously defined at "{self.symbol_table[symbol].location}"')
        self.symbol_table[symbol.qualified_identifier] = symbol
        if duplicate_allowed:
            return symbol
    
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
        obj.dependend_files.add(module_path)
    target_module_id = SymbolIdentifier(gimport.target_module_name, SymbolType.MODULE)
    imported_symbol_id = module.qualified_identifier.append(target_module_id)
    obj.references[gimport.location.uri][gimport.location.range] = target_module_id
    obj.symbol_table[imported_symbol_id] = target_module_id

def _compile_sym(module: ModuleSymbol, sym: Symi, obj: StexObject):
    pass

def _compile_symdef(module: ModuleSymbol, symdef: Symdef, obj: StexObject):
    pass

def _compile_mhmodnl(mhmodnl: Mhmodnl, obj: StexObject, parsed_file: ParsedFile):
    module_id = SymbolIdentifier(mhmodnl.name.text, SymbolType.MODULE)
    binding = BindingSymbol(mhmodnl.location, lang=mhmodnl.lang.text, module=module_id)
    obj.add_symbol(binding)
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
    obj.references[defi.location.uri][defi.location.range] = symbol_id

def _compile_trefi(binding: BindingSymbol, trefi: Trefi, obj: StexObject):
    target_module, _, module_range, symbol_range = trefi.parse_annotations()
    if target_module is None:
        module_id = binding.parent
    else:
        target_id = SymbolIdentifier(target_module, SymbolType.MODULE)
        module_id = binding.parent.append(target_id)
    symbol_id = module_id.append(SymbolIdentifier(trefi.target_symbol, SymbolType.SYMBOL))
    obj.references[trefi.location.uri][trefi.location.range] = symbol_id
    if module_range is not None:
        module_location = trefi.location.replace(positionOrRange=module_range)
        obj.references[module_location.uri][module_location.range] = module_id