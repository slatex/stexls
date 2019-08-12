from __future__ import annotations
from typing import Optional, Dict, Iterator, Union
import re
from functools import partial
import sys

from trefier.misc.location import *
from trefier.parser.latex_parser import LatexParser
from trefier.linting.exceptions import *
from trefier.linting.identifiers import *
from trefier.linting.symbols import *
from trefier.linting.symbols import _node_to_location

__all__ = ['Document']


class Document:
    def get_import_location(self, module: Union[ModuleIdentifier, str]) -> Optional[GimportSymbol]:
        """ Find gimport by module name or return None """
        for gimport in self.gimports:
            if str(gimport.imported_module) == str(module):
                return gimport
        return None

    @property
    def module_identifier(self):
        if self.module:
            return self.module.module
        elif self.binding:
            return self.binding.module
    
    @property
    def exception_summary(self) -> Iterator[Tuple[Range, str]]:
        yield from self.exceptions
        for trefi in self.trefis or ():
            yield from map((lambda x: (trefi.range, x)), trefi.errors)
        for defi in self.defis or ():
            yield from map((lambda x: (defi.range, x)), defi.errors)
        for symi in self.symis or ():
            yield from map((lambda x: (symi.range, x)), symi.errors)
        if self.module:
            yield from map((lambda x: (self.module.range, x)), self.module.errors)
        if self.binding:
            yield from map((lambda x: (self.binding.range, x)), self.binding.errors)
    
    def __getstate__(self):
        return (
            self.file,
            self.exceptions,
            self.module,
            self.binding,
            self.syntax_errors,
            self.success,
            self.symis,
            self.gimports,
            self.trefis,
            self.defis)
    
    def __setstate__(self, state):
        self.parser = None
        (self.file,
         self.exceptions,
         self.module,
         self.binding,
         self.syntax_errors,
         self.success,
         self.symis,
         self.gimports,
         self.trefis,
         self.defis) = state

    def __init__(self, file: str, ignore_exceptions: bool = True):
        self.file = file
        self.exceptions: List[Tuple[Range, Exception]] = []
        self.parser: Optional[LatexParser] = None
        self.module: Optional[ModuleDefinitonSymbol] = None
        self.binding: Optional[ModuleBindingDefinitionSymbol] = None
        self.syntax_errors: Optional[Dict[Location, Dict[str, object]]] = None
        self.success = False
        self.symis = None
        self.gimports = None
        self.trefis = None
        self.defis = None
        try:
            self.parser = LatexParser(self.file, ignore_exceptions=False)
            self.syntax_errors = self.parser.syntax_errors
            if self.parser.success:
                def catcher(symbol_type_constructor):
                    def wrapper(node):
                        try:
                            symbol = symbol_type_constructor(node)
                            return symbol
                        except Exception as e:
                            if not ignore_exceptions:
                                raise
                            self.exceptions.append((_node_to_location(node).range, e))
                    return wrapper

                self.symis: List[SymiSymbol] = list(
                    filter(None, map(catcher(SymiSymbol.from_node),
                                     self.parser.root.finditer(SymiSymbol.SYM_PATTERN))))

                self.gimports: List[GimportSymbol] = list(
                    filter(None, map(catcher(GimportSymbol.from_node),
                                     self.parser.root.finditer(GimportSymbol.GIMPORT_PATTERN))))

                self.trefis: List[TrefiSymbol] = list(
                    filter(None, map(catcher(TrefiSymbol.from_node),
                                     self.parser.root.finditer(TrefiSymbol.TREFI_PATTERN))))

                self.defis: List[DefiSymbol] = list(
                    filter(None, map(catcher(DefiSymbol.from_node),
                                     self.parser.root.finditer(DefiSymbol.DEFI_PATTERN))))

                modules: List[ModuleDefinitonSymbol] = list(
                    filter(None, map(catcher(ModuleDefinitonSymbol.from_node),
                                     self.parser.root.finditer(ModuleDefinitonSymbol.MODULE_PATTERN))))

                if len(modules) >= 1:
                    self.module = modules[0]

                bindings: List[ModuleBindingDefinitionSymbol] = list(
                    filter(None, map(catcher(ModuleBindingDefinitionSymbol.from_node),
                                     self.parser.root.finditer(ModuleBindingDefinitionSymbol.MODULE_BINDING_PATTERN))))

                if len(bindings) >= 1:
                    self.binding = bindings[0]
                
                if self.binding is not None and self.module is not None:
                    raise LinterException(f'File must not contain binding and module definition!')

                self.success = True

        except Exception as e:
            self.exceptions.append((Range(Position()), e))
