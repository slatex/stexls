from __future__ import annotations
from typing import Dict, Optional, Set, Union
import itertools
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
        self.symbol_table: Dict[SymbolIdentifier, List[Symbol]] = defaultdict(list)
        self.references: Dict[Path, Dict[Range, SymbolIdentifier]] = defaultdict(dict)
        self.errors: Dict[Location, List[Exception]] = defaultdict(list)

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
    
    def add_dependency(self, location: Location, file: Path):
        self.dependend_files[file].add(location)
    
    def add_reference(self, location: Location, referenced_id: SymbolIdentifier):
        self.references[location.uri][location.range] = referenced_id

    def add_symbol(self, symbol: Symbol, export: bool = False, duplicate_allowed: bool = False):
        symbol.access_modifier = AccessModifier.PUBLIC if export else AccessModifier.PRIVATE
        if symbol.qualified_identifier in self.symbol_table:
            if duplicate_allowed:
                for duplicate in self.symbol_table[symbol.qualified_identifier]:
                    if duplicate.access_modifier != symbol.access_modifier:
                        raise CompilerException(
                            f'Duplicate symbol definition of {symbol.qualified_identifier}'
                            f' at "{symbol.location}" and "{duplicate.location}"'
                            f' where access modifiers are different:'
                            f' {symbol.access_modifier.name} vs. {duplicate.access_modifier.name}')
            else:
                locs = ', '.join(dup.location.one.format_link() for dup in self.symbol_table[symbol.qualified_identifier])
                raise CompilerException(
                        f'Duplicate symbol definition of {symbol.qualified_identifier}:'
                        f'Previously defined at {locs}')
        self.symbol_table[symbol.qualified_identifier].append(symbol)

    @staticmethod
    def compile(parsed: ParsedFile) -> Optional[StexObject]:
        obj = StexObject()
        obj.errors = parsed.errors.copy()
        obj.compiled_files.add(parsed.path)
        if len(parsed.mhmodnls) > 1:
            raise CompilerException(f'Too many language bindings in file: Found {len(parsed.mhmodnls)}')
        if len(parsed.modsigs) > 1:
            raise CompilerException(f'Too many module signatures in file: Found {len(parsed.modsigs)}')
        number_of_roots = len(parsed.mhmodnls) + len(parsed.modsigs) 
        if number_of_roots == 0 and not parsed.errors:
            return
        if number_of_roots > 1:
            raise CompilerException(f'Mixing of module signature and binding not allowed.')
        for modsig in parsed.modsigs:
            _compile_modsig(modsig, obj, parsed)
        for mhmodnl in parsed.mhmodnls:
            _compile_mhmodnl(mhmodnl, obj, parsed)
        return obj


def _compile_modsig(modsig: Modsig, obj: StexObject, parsed_file: ParsedFile):
    for invalid_environment in itertools.chain(
        parsed_file.mhmodnls,
        parsed_file.defis,
        parsed_file.trefis):
        obj.errors[invalid_environment.location] = Warning(f'Invalid environment of type {type(invalid_environment).__name__} in mhmodnl.')
    module = ModuleSymbol(modsig.location, modsig.name.text)
    obj.add_symbol(module, export=True)
    for gimport in parsed_file.gimports:
        try:
            _compile_gimport(module, gimport, obj)
        except Exception as e:
            obj.errors[gimport.location].append(e)
    for sym in parsed_file.syms:
        try:
            _compile_sym(module, sym, obj)
        except Exception as e:
            obj.errors[sym.location].append(e)
    for symd in parsed_file.symdefs:
        try:
            _compile_symdef(module, symd, obj)
        except Exception as e:
            obj.errors[symd.location].append(e)

def _compile_gimport(module: ModuleSymbol, gimport: GImport, obj: StexObject):
    module_path = gimport.module_path
    target_module_placeholder = PlaceholderSymbol(
        gimport.location, gimport.target_module_name, module.qualified_identifier)
    referenced_module_id = SymbolIdentifier(gimport.target_module_name, SymbolType.MODULE)
    obj.add_symbol(target_module_placeholder, export=True)
    obj.add_dependency(gimport.location, module_path)
    obj.add_reference(gimport.location, referenced_module_id)

def _compile_sym(module: ModuleSymbol, sym: Symi, obj: StexObject):
    symbol = DefSymbol(sym.location, sym.name, module.qualified_identifier)
    obj.add_symbol(symbol, export=True)

def _compile_symdef(module: ModuleSymbol, symdef: Symdef, obj: StexObject):
    symbol = DefSymbol(symdef.location, symdef.name, module.qualified_identifier)
    obj.add_symbol(symbol, duplicate_allowed=True, export=True)

def _compile_mhmodnl(mhmodnl: Mhmodnl, obj: StexObject, parsed_file: ParsedFile):
    module_id = SymbolIdentifier(mhmodnl.name.text, SymbolType.MODULE)
    name_location = mhmodnl.location.replace(positionOrRange=mhmodnl.name.range)
    obj.add_reference(name_location, module_id)
    obj.add_dependency(name_location, mhmodnl.path_to_module_file)
    for invalid_environment in itertools.chain(
        parsed_file.modsigs,
        parsed_file.gimports,
        parsed_file.symdefs,
        parsed_file.syms):
        obj.errors[invalid_environment.location] = Warning(f'Invalid environment of type {type(invalid_environment).__name__} in mhmodnl.')
    for defi in parsed_file.defis:
        try:
            _compile_defi(module_id, defi, obj)
        except Exception as e:
            obj.errors[defi.location] = e
    for trefi in parsed_file.trefis:
        try:
            _compile_trefi(module_id, trefi, obj)
        except Exception as e:
            obj.errors[trefi.location] = e

def _compile_defi(module: SymbolIdentifier, defi: Defi, obj: StexObject):
    defi_id = SymbolIdentifier(defi.name, SymbolType.SYMBOL)
    symbol_id = module.append(defi_id)
    obj.add_reference(defi.location, symbol_id)

def _compile_trefi(module_id: SymbolIdentifier, trefi: Trefi, obj: StexObject):
    target_module, target_symbol, module_range, _ = trefi.parse_annotations()
    if target_module:
        module_id = SymbolIdentifier(target_module, SymbolType.MODULE)
        module_location = trefi.location.replace(positionOrRange=module_range)
        obj.add_reference(module_location, module_id)
    target_symbol_id = module_id.append(SymbolIdentifier(target_symbol or trefi.target_symbol, SymbolType.SYMBOL))
    obj.add_reference(trefi.location, target_symbol_id)
