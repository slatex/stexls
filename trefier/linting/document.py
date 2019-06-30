from __future__ import annotations
from typing import Optional, Union

from ..misc.location import *
from ..parser.latex_parser import LatexParser

from .exceptions import *
from .identifiers import *
from .symbols import *

__all__ = ['Document']


class Document:
    def get_import_location(self, module: Union[ModuleIdentifier, str]) -> Optional[GimportSymbol]:
        """ Find gimport by module name or return None """
        for gimport in self.gimports:
            if str(gimport.imported_module) == str(module):
                return gimport
        return None

    def __init__(self, file: str, ignore_exceptions: bool = True):
        self.file = file
        self.exceptions: List[Exception] = []
        self.module: Optional[ModuleDefinitonSymbol] = None
        self.binding: Optional[ModuleBindingDefinitionSymbol] = None
        self.success = False
        self.module_identifier = ModuleIdentifier.from_file(file)
        parser = LatexParser(file)
        if parser.exception:
            self.exceptions.append(parser.exception)
        if parser.success:
            def catcher(symbol_type_constructor):
                def wrapper(node):
                    try:
                        symbol = symbol_type_constructor(node)
                        return symbol
                    except Exception as e:
                        if not ignore_exceptions:
                            raise
                        self.exceptions.append(e)
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

            if len(modules) > 1:
                raise LinterException(f'{modules[0]} Multiple modules in file "{file}":'
                                      f' More at {modules[1]}')

            if len(modules) == 1:
                self.module, = modules

            bindings: List[ModuleBindingDefinitionSymbol] = list(
                filter(None, map(catcher(ModuleBindingDefinitionSymbol.from_node),
                                 parser.root.finditer(ModuleBindingDefinitionSymbol.MODULE_BINDING_PATTERN))))

            if len(bindings) > 1:
                raise LinterException(f'{bindings[0]} Multiple bindings in file "{file}":'
                                      f' More at {bindings[1]}')

            if len(bindings) == 1:
                self.binding, = bindings

            if self.binding and self.module:
                raise LinterException(f'{file} Files may not include a module and a binding at the same time:'
                                      f' Binding at {self.binding}, and module at {self.module}')
            self.success = True
