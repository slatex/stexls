from __future__ import annotations
from .exceptions import *

__all__ = ['ModuleIdentifier', 'SymbolIdentifier']


class ModuleIdentifier:
    def __init__(self, base: str, repository_name: str, module_name: str):
        self.base = base
        self.repository_name = repository_name
        self.module_name = module_name

    def __repr__(self):
        return f'{self.base}/{self.repository_name}/{self.module_name}'

    def __hash__(self):
        return hash(self.base) ^ hash(self.repository_name) ^ hash(self.module_name)

    def __eq__(self, other: ModuleIdentifier):

        return other is not None and (self.base == other.base
                                      and self.repository_name == other.repository_name
                                      and self.module_name == other.module_name)

    @property
    def without_name(self) -> str:
        """ Returns the string for the identifier without the module name at the end. """
        return self.base + '/' + self.repository_name

    @staticmethod
    def from_file(file: str) -> ModuleIdentifier:
        parts = file.split('/')

        if parts[-2] != 'source' or len(parts) < 4:
            raise LinterModuleFromFilenameException.create()

        return ModuleIdentifier(
            base=parts[-4],
            repository_name=parts[-3],
            module_name=parts[-1].split('.')[0],
        )

    @staticmethod
    def from_id_string(id: str) -> ModuleIdentifier:
        parts = id.split('/')
        assert len(parts) == 3, "Invalid id string"
        return ModuleIdentifier(*parts)


class SymbolIdentifier:
    def __init__(self, symbol_name: str, module: ModuleIdentifier = None):
        """ An unique identifier for a symbol: base/repo/module/symbol """
        self.symbol_name = symbol_name
        self.module = module

    def __repr__(self):
        return f'{self.module}/{self.symbol_name}'
