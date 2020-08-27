from __future__ import annotations
import os
from typing import Set, Optional, Dict, List, Union
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
    'ScopeSymbol',
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


class DuplicateSymbolDefinedException(Exception):
    pass


class Symbol:
    def __init__(
        self,
        location: Location,
        name: str):
        """ Initializes a symbol.

        Parameters:
            location: Location of where this symbol is defined.
                The range of this location should only contain the text, which is selected
                when revealing this symbol.
            name: Identifier of this symbol relative to it's parent.
        """
        self.name = name
        self.parent: Optional[Symbol] = None
        self.children: Dict[str, List[Symbol]] = dict()
        self.location = location
        self.access_modifier = AccessModifier.PUBLIC

    def copy(self) -> Symbol:
        ' Creates a copy. '
        symbol = Symbol(self.location.copy() if self.location else None, self.name)
        symbol.access_modifier = self.access_modifier
        for children in self.children.values():
            for child in children:
                symbol.add_child(child.copy(), alternative=len(children)>1)
        return symbol

    @property
    def depth(self) -> int:
        if self.parent:
            return self.parent.depth + 1
        return 0

    def traverse(self, enter, exit=None):
        ' Traverse the symbol hierarchy. Executes enter and exit for each symbol. '
        if enter:
            enter(self)
        for child_alternatives in self.children.values():
            for child in child_alternatives:
                child.traverse(enter, exit)
        if exit:
            exit(self)

    @property
    def qualified(self) -> Tuple[str]:
        if self.parent:
            return (*self.parent.qualified, self.name)
        return (self.name,)

    @property
    def current_module(self) -> Optional[str]:
        ' Find the first parent ModuleSymbol. '
        if self.parent:
            return self.parent.current_module
        return None

    def add_child(self, child: Symbol, alternative: bool = False):
        """ Adds a child symbol.

        Parameters:
            child: Child to add.
            alternative: If set to true, allows for duplicate definitions.

        Raises:
            If the child already has a parent or rises DuplicateSymbolDefinedException
            if a symbol with the same name is already defined and alternatives are not allowed.
        """
        if child.parent:
            raise ValueError('Attempting to add child symbol which already has a parent.')
        if not alternative and child.name in self.children:
            raise DuplicateSymbolDefinedException(f'Symbol with name "{child.name}" already added.')
        child.parent = self
        self.children.setdefault(child.name, []).append(child)

    def lookup(self, qualified_identifier: Union[str, List[str]]) -> List[Symbol]:
        """ Symbol lookup searches for symbols with a given qualified identifier.
        Special about the lookup operation is, that the first identifier must be in the symbol table
        of a parent, while all others must be part of the children.

        Parameters:
            qualified_identifier: Qualified identifier of the symbol.

        Returns:
            All symbols with the specified qualified id.

        Raises:
            Raises ValueError if the symbol was not found in this symbol or any parent.
            Raises ValueError if any identifier before the last in the list, result in
            non-unique symbols.
        """
        if isinstance(qualified_identifier, str):
            qualified_identifier = [qualified_identifier]
        children = self.children.get(qualified_identifier[0], [])
        if len(qualified_identifier) > 1:
            if len(children) > 1:
                raise ValueError(f'Unable to resolve {qualified_identifier}: Id not unique.')
            for child in children:
                # for-loop, but only the first is relevant
                return child.find(qualified_identifier[1:])
        if children:
            return children
        if self.parent:
            return self.parent.lookup(qualified_identifier)
        raise ValueError(f'Symbol "{qualified_identifier}" not found.')

    def find(self, qualified_identifier: Union[str, List[str]]) -> List[Symbol]:
        """ Searches for a child symbol with a given name inside this symbol table and all symbol tables resolved on the way.
        Parent lookup is not performed.

        Parameters:
            qualified_identifier: Qualified identifier of the child symbol.

        Returns:
            Symbol with the specified qualified identifier.

        Raises:
            Raises ValueError if the symbol was not found.
            Raises ValueError if a identifier that is not the last identifier resolves to multiple symbols.
        """
        if isinstance(qualified_identifier, str):
            qualified_identifier = [qualified_identifier]
        children = self.children.get(qualified_identifier[0])
        if len(qualified_identifier) > 1:
            if len(children) > 1:
                raise ValueError(f'Unable to resolve {qualified_identifier}: Id not unique.')
            for child in children:
                return child.find(qualified_identifier[1:])
        if children:
            return children
        raise ValueError(f'Symbol "{qualified_identifier}" not found.')

    def __repr__(self):
        return f'[{self.access_modifier.value} Symbol {self.name}]'


class ModuleSymbol(Symbol):
    def __init__(
        self,
        module_type: ModuleType,
        location: Location,
        name: str):
        """ New module signature symbol.

        Parameters:
            module_type: The latex environment type used to define this symbol.
        """
        super().__init__(location, name)
        self.module_type = module_type

    def copy(self) -> ModuleSymbol:
        ' Copies this module symbol including added children. '
        module = ModuleSymbol(self.module_type, self.location.copy(), self.name)
        module.access_modifier = self.access_modifier
        for children in self.children.values():
            for child in children:
                module.add_child(child.copy(), alternative=len(children)>1)
        return module

    @property
    def current_module(self) -> ModuleSymbol:
        return self

    def __repr__(self):
        return f'[ModuleSymbol "{self.name}"/{self.module_type.name}]'


class VerbSymbol(Symbol):
    def __init__(
        self,
        verb_type: VerbType,
        location: Location,
        name: str,
        noverb: bool = False,
        noverbs: Set[str] = None):
        """ New Verb symbol.

        Parameters:
            module:
            verb_type: Latex environment used to define this symbol.
            noverb: If True, then this verb symbol should not have any references in any language.
            noverbs: Set of languages this symbol should not be referenced from.
        """
        super().__init__(location, name)
        self.verb_type = verb_type
        self.noverb = noverb
        self.noverbs = noverbs or set()

    def __repr__(self):
        return f'[VerbSymbol "{self.name}"/{self.verb_type.name}]'

    def copy(self) -> VerbSymbol:
        ' Copies this symbol including children. '
        verb = VerbSymbol(self.verb_type, self.location.copy(), self.name, self.noverb, self.noverbs.copy())
        verb.access_modifier = self.access_modifier
        for children in self.children.values():
            for child in children:
                verb.add_child(child.copy(), alternative=len(children)>1)
        return verb


class ScopeSymbol(Symbol):
    COUNTER=0
    def __init__(self, location: Location):
        super().__init__(location, f'__ANONYMOUS_SCOPE{ScopeSymbol.COUNTER}__')
        ScopeSymbol.COUNTER += 1

    def copy(self) -> ScopeSymbol:
        ' Creates a shallow copy without parent and child information. '
        scope = ScopeSymbol(self.location.copy())
        scope.access_modifier = self.access_modifier
        for children in self.children.values():
            for child in children:
                scope.add_child(child.copy(), alternative=len(children)>1)
        return scope
