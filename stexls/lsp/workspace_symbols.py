from typing import Set, Dict, Tuple
from pathlib import Path
from stexls.stex.symbols import *
from stexls.stex.compiler import StexObject

class WorkspaceSymbols:
    """ This class is a accumulator for all symbols in unlinked StexObjects added to the workspace.

    The symbols are stored as strings in order to make it easy for difflib.get_close_matches to create
    some suggestions for similarly named symbols.

    Usage:
        Call @WorkspaceSymbols.add(StexObject) the first time a file is compiled.
        If the file is changed, remove it first by calling @WorkspaceSymbols.remove(StexObject).
        Then after the changed file is compiled again, add it again with @WorkspaceSymbols.add(StexObject).

        All qualified symbol names can be accessed using @WorkspaceSymbols.symbols.
    """
    def __init__(self, resolution_char: str = '?') -> None:
        self.resolution_char = resolution_char
        # symbol providers is a dict from path to the object because StexObject is not a ValueType.
        self.symbol_providers: Dict[Path, StexObject] = dict()
        self.symbols: Dict[str, Set[StexObject]] = dict()

    def add(self, obj: StexObject) -> bool:
        """ Adds @obj as a provider of symbol names.
        The @obj should be unlinked and only contain it's own symbols.

        Raises:
            ValueError: If the object is already added and was not removed properly.
        """
        if obj in self.symbol_providers:
            raise ValueError(f'Symbol provider already added: {obj}')
        self.symbol_providers[obj.file] = obj
        for symbol in obj.symbol_table.flat():
            symbol_name = self.resolution_char.join(symbol.qualified)
            self.symbols.setdefault(symbol_name, set()).add(obj)

    def remove(self, file: Path) -> bool:
        " Removes @obj as a provider of symbol names. Returns True if the file was removed. "
        if file not in self.symbol_providers:
            return False
        obj = self.symbol_providers[file]
        for symbol in obj.symbol_table.flat():
            qualified_string = self.resolution_char.join(symbol.qualified)
            self.symbols[qualified_string].remove(obj)
            if not self.symbols[qualified_string]:
                del self.symbols[qualified_string]
        del self.symbol_providers[file]
        return True

__all__ = ['WorkspaceSymbols']
