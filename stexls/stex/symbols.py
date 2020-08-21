from __future__ import annotations
import os
from typing import Set, List, Optional, Tuple
from enum import Enum
from pathlib import Path
from stexls.vscode import Location, Range, DocumentSymbol


__all__ = [
    'AccessModifier',
    'ModuleType',
    'VerbType',
    'Symbol',
    'ModuleSymbol',
    'VerbSymbol',
]


class AccessModifier(Enum):
    PUBLIC='public'
    PRIVATE='private'
    PROTECTED='protected'


class ModuleType(Enum):
    MODSIG='modsig'
    MODULE='module'


class VerbType(Enum):
    DEF='def'
    DREF='dref'
    SYMDEF='symdef'
    SYM='sym'


class Symbol:
    def __init__(
        self,
        location: Location,
        name: str,
        range: Range = None):
        """ Initializes a symbol.

        Parameters:
            location: Location of where this symbol is defined.
                The range of this location should only contain the text, which is selected
                when revealing this symbol.
            name: Identifier of this symbol relative to it's parent.
            range: The range enclosing this symbol not including leading/trailing whitespace but everything else
                like comments. This information is typically used to determine if the clients cursor is
                inside the symbol to reveal in the symbol in the UI.
        """
        self.name: str = name
        self.parent: Symbol = None
        self.children: List[Symbol] = []
        self.location: Location = location
        self.access_modifier: AccessModifier = AccessModifier.PRIVATE
        self.range = range

    def add_child(self, child: Symbol):
        ' Adds a child symbol. Raises if the child already has a parent. '
        if child.parent:
            raise ValueError('Attempting to add child symbol which already has a parent.')
        child.parent = self
        self.children.append(child)

    def get_repository_identifier(self, root: Path) -> str:
        ' Returns the repository identifier (e.g.: smglom/repo) assuming this symbol is contained in <root>. '
        # root/<smglom/repo>/source/module.tex
        return list(self.location.path.relative_to(root).parents)[-3].as_posix()

    def get_path(self, root: Path) -> Path:
        ' Returns the path= argument for importmodules. '
        rel = self.location.path.relative_to(root)
        file = rel.relative_to(list(rel.parents)[-4])
        return file.parent / file.stem

    def __repr__(self):
        return f'[{self.access_modifier.value} Symbol {self.name}]'


class ModuleSymbol(Symbol):
    def __init__(
        self,
        module_type: ModuleType,
        location: Location,
        name: str,
        range: Range = None):
        """ New module signature symbol.

        Parameters:
            module_type: The latex environment type used to define this symbol.
        """
        super().__init__(location, name, range)
        self.module_type = module_type


class VerbSymbol(Symbol):
    def __init__(
        self,
        module: str,
        verb_type: VerbType,
        location: Location,
        name: str,
        range: Range = None,
        noverb: bool = False,
        noverbs: Set[str] = None):
        """ New Verb symbol.

        Parameters:
            module:
            verb_type: Latex environment used to define this symbol.
            noverb: If True, then this verb symbol should not have any references in any language.
            noverbs: Set of languages this symbol should not be referenced from.
        """
        super().__init__(location, name, range)
        self.module = module
        self.verb_type = verb_type
        self.noverb = noverb
        self.noverbs = noverbs or set()

