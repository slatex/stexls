from __future__ import annotations
import os
from typing import Set, Optional, Dict, List, Union, Tuple
from enum import Enum
from pathlib import Path
from stexls.vscode import Location, Range, DocumentSymbol
from .exceptions import DuplicateSymbolDefinedException


__all__ = [
    'AccessModifier',
    'ModuleType',
    'DefType',
    'Symbol',
    'ModuleSymbol',
    'BindingSymbol',
    'DefSymbol',
    'ScopeSymbol',
]


class AccessModifier(Enum):
    PUBLIC='public'
    PRIVATE='private'
    PROTECTED='protected'


class ModuleType(Enum):
    MODSIG='modsig'
    MODULE='module'


class DefType(Enum):
    DEF='def'
    DREF='dref'
    SYMDEF='symdef'
    SYM='sym'


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

    def is_parent_of(self, other: Symbol) -> bool:
        ' Returns true if this symbol is a parent of the other symbol. '
        parent = other.parent
        while parent is not None:
            if self == parent:
                return True
            parent = parent.parent
        return False

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

    def get_current_module(self) -> Optional[ModuleSymbol]:
        ' Find the first parent ModuleSymbol. '
        if self.parent:
            return self.parent.get_current_module()
        return None

    def get_current_binding(self) -> Optional[BindingSymbol]:
        if self.parent:
            return self.parent.get_current_binding()
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
            raise DuplicateSymbolDefinedException(f'Symbol with name "{child.name}" already added: {self.location.format_link()}')
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
        return []

    def find(self, qualified_identifier: Union[str, List[str]]) -> List[Symbol]:
        """ Searches for a child symbol with a given name inside this symbol table and all symbol tables resolved on the way.
        Parent lookup is not performed.

        Parameters:
            qualified_identifier: Qualified identifier of the child symbol.

        Returns:
            Symbol with the specified qualified identifier.

        Raises:
            Raises ValueError if a identifier that is not the last identifier resolves to multiple symbols.
        """
        if isinstance(qualified_identifier, str):
            qualified_identifier = [qualified_identifier]
        children = self.children.get(qualified_identifier[0])
        if not children:
            return []
        if len(qualified_identifier) > 1:
            if len(children) > 1:
                raise ValueError(f'Unable to resolve {qualified_identifier}: Id not unique.')
            for child in children:
                return child.find(qualified_identifier[1:])
        return children

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
        ' Copies this module symbol excluding parent and child structure. '
        cpy = ModuleSymbol(self.module_type, self.location.copy(), self.name)
        cpy.access_modifier = self.access_modifier
        return cpy

    def get_current_module(self) -> ModuleSymbol:
        return self

    def __repr__(self):
        return f'[ModuleSymbol "{self.name}"/{self.module_type.name}]'


class DefSymbol(Symbol):
    def __init__(
        self,
        def_type: DefType,
        location: Location,
        name: str,
        noverb: bool = False,
        noverbs: Set[str] = None):
        """ New Verb symbol.

        Parameters:
            module:
            def_type: Latex environment used to define this symbol.
            noverb: If True, then this verb symbol should not have any references in any language.
            noverbs: Set of languages this symbol should not be referenced from.
        """
        super().__init__(location, name)
        self.def_type = def_type
        self.noverb = noverb
        self.noverbs = noverbs or set()

    def __repr__(self):
        return f'[{self.access_modifier.name} DefSymbol "{self.name}"/{self.def_type.name}]'

    def copy(self) -> DefSymbol:
        ' Shallow copy of this symbol without parent and child structure. '
        cpy = DefSymbol(self.def_type, self.location.copy(), self.name, self.noverb, self.noverbs.copy())
        cpy.access_modifier = self.access_modifier
        return cpy


class BindingSymbol(Symbol):
    def __init__(self, location: Location, module: str, lang: str):
        super().__init__(location, module)
        self.lang = lang

    def get_current_binding(self) -> BindingSymbol:
        return self

    def copy(self) -> BindingSymbol:
        cpy = BindingSymbol(self.location.copy(), self.name, self.lang)
        cpy.access_modifier = self.access_modifier
        return cpy

    def __repr__(self):
        return f'[{self.access_modifier.name} BindingSymbol {self.name}.{self.lang}]'


class ScopeSymbol(Symbol):
    COUNTER=0
    def __init__(self, location: Location):
        super().__init__(location, f'__ANONYMOUS_SCOPE{ScopeSymbol.COUNTER}__')
        ScopeSymbol.COUNTER += 1

    def copy(self) -> ScopeSymbol:
        ' Creates a shallow copy without parent and child information. '
        cpy = ScopeSymbol(self.location.copy())
        cpy.access_modifier = self.access_modifier
        return cpy
