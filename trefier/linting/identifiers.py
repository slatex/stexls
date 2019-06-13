from __future__ import annotations
from .exceptions import *

__all__ = ['ModuleIdentifier', 'SymbolIdentifier']


class ModuleIdentifier:
    def __init__(self, base: str, repository_name: str, module_name: str):
        if not (base or repository_name or module_name):
            raise Exception(f'Module identifier arguments may not be falsy: Found'
                            f' "{base or "<undefined>"}'
                            f'/{repository_name or "<undefined>"}'
                            f'/{module_name or "<undefined>"}"')
        self.base = base
        self.repository_name = repository_name
        self.module_name = module_name

    def __repr__(self):
        return f'{self.base}/{self.repository_name}/{self.module_name}'

    def __hash__(self):
        return hash(self.base) ^ hash(self.repository_name) ^ hash(self.module_name)

    def __eq__(self, other: ModuleIdentifier):
        return (self.base == other.base
                and self.repository_name == other.repository_name
                and self.module_name == other.module_name)

    @staticmethod
    def from_file(file: str) -> ModuleIdentifier:
        parts = file.split('/')

        if parts[-2] != 'source' or len(parts) < 4:
            raise LinterModuleFromFilenameException.create(file)

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
