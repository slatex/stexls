from __future__ import annotations
from typing import Optional, Dict, Iterator
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
        if hasattr(self, 'trefis'):
            for trefi in self.trefis:
                yield from map((lambda x: (trefi.range, x)), trefi.errors)
        if hasattr(self, 'defis'):
            for defi in self.defis:
                yield from map((lambda x: (defi.range, x)), defi.errors)
        if hasattr(self, 'symis'):
            for symi in self.symis:
                yield from map((lambda x: (symi.range, x)), symi.errors)
        if hasattr(self, 'module') and self.module:
            yield from map((lambda x: (self.module.range, x)), self.module.errors)
        if hasattr(self, 'binding') and self.binding:
            yield from map((lambda x: (self.binding.range, x)), self.binding.errors)

    def __init__(self, file: str, ignore_exceptions: bool = True):
        self.file = file
        self.exceptions: List[Tuple[Range, Exception]] = []
        self.module: Optional[ModuleDefinitonSymbol] = None
        self.binding: Optional[ModuleBindingDefinitionSymbol] = None
        self.syntax_errors: Optional[Dict[Location, Dict[str, object]]] = None
        self.success = False
        try:
            parser = LatexParser(file, ignore_exceptions=False)
            self.syntax_errors = parser.syntax_errors
            if parser.success:
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
                                     parser.root.finditer(SymiSymbol.SYM_PATTERN))))

                self.gimports: List[GimportSymbol] = list(
                    filter(None, map(catcher(GimportSymbol.from_node),
                                     parser.root.finditer(GimportSymbol.GIMPORT_PATTERN))))

                self.trefis: List[TrefiSymbol] = list(
                    filter(None, map(catcher(TrefiSymbol.from_node),
                                     parser.root.finditer(TrefiSymbol.TREFI_PATTERN))))

                self.defis: List[DefiSymbol] = list(
                    filter(None, map(catcher(DefiSymbol.from_node),
                                     parser.root.finditer(DefiSymbol.DEFI_PATTERN))))

                modules: List[ModuleDefinitonSymbol] = list(
                    filter(None, map(catcher(ModuleDefinitonSymbol.from_node),
                                     parser.root.finditer(ModuleDefinitonSymbol.MODULE_PATTERN))))

                if len(modules) >= 1:
                    self.module = modules[0]

                bindings: List[ModuleBindingDefinitionSymbol] = list(
                    filter(None, map(catcher(ModuleBindingDefinitionSymbol.from_node),
                                     parser.root.finditer(ModuleBindingDefinitionSymbol.MODULE_BINDING_PATTERN))))

                if len(bindings) >= 1:
                    self.binding = bindings[0]

                self.success = self.binding != self.module
        except Exception as e:
            self.exceptions.append((Range(Position()), e))
