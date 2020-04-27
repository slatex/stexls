from __future__ import annotations
from typing import Set
from enum import Enum
from pathlib import Path
from stexls.util.vscode import Location, Range

__all__ = [
    'SymbolType',
    'AccessModifier',
    'DefinitionType',
    'SymbolIdentifier',
    'Symbol',
    'ModuleSymbol',
    'BindingSymbol',
    'VerbSymbol',
]


class SymbolType(Enum):
    SYMBOL='symbol'
    MODULE='module'
    BINDING='binding'


class AccessModifier(Enum):
    PUBLIC='public'
    PRIVATE='private'
    PROTECTED='protected'


class DefinitionType(Enum):
    MODSIG='modsig'
    MODULE='module'
    DEFI='defi'
    SYMDEF='symdef'
    SYM='sym'
    BINDING='binding'


class SymbolIdentifier:
    def __init__(self, identifier: str, symbol_type: SymbolType):
        self.identifier = identifier
        self.symbol_type = symbol_type
    
    @property
    def typed_identifier(self):
        return self.identifier + '/' + self.symbol_type.name
    
    def prepend(self, identifier: str, delim: str = '?'):
        return SymbolIdentifier(identifier + delim + self.identifier, self.symbol_type)
    
    def append(self, identifier: SymbolIdentifier):
        return identifier.prepend(self.identifier)

    def __hash__(self):
        return hash(self.typed_identifier)

    def __eq__(self, other: SymbolIdentifier):
        if not isinstance(other, SymbolIdentifier):
            return False
        return self.identifier == other.identifier and self.symbol_type == other.symbol_type
    
    def __repr__(self):
        return self.typed_identifier


class Symbol:
    def __init__(
        self,
        location: Location,
        identifier: SymbolIdentifier,
        parent: SymbolIdentifier,
        definition_type: DefinitionType,
        full_range: Range = None):
        """ Initializes a symbol.

        Parameters:
            location: Location of where this symbol is defined.
            identifier: Identifier of this symbol relative to it's parent.
            parent: The identifier of the parent symbol this symbol is scoped to.
            definition_type: The way this symbol was defined with.
            full_range: Range to be revealed when jumping to this symbol.
        """
        self.identifier: SymbolIdentifier = identifier
        self.parent: SymbolIdentifier = parent
        self.location: Location = location
        self.access_modifier: AccessModifier = AccessModifier.PRIVATE
        self.definition_type = definition_type
        self.full_range = full_range

    @property
    def qualified_identifier(self) -> SymbolIdentifier:
        """ The fully qualified identifier for this symbol.
        
        >>> symbol = Symbol(None, SymbolIdentifier('child', SymbolType.SYMBOL), SymbolIdentifier('parent', SymbolType.MODULE))
        >>> symbol.parent
        'parent/MODULE'
        >>> symbol.identifier'
        'child/SYMBOL'
        >>> symbol.qualified_identifier
        'parent?child/SYMBOL'
        """
        if self.parent is None:
            return self.identifier
        return self.parent.append(self.identifier)

    def __hash__(self):
        return hash(self.qualified_identifier.typed_identifier)
    
    def __eq__(self, other: Symbol):
        if not isinstance(other, Symbol):
            return False
        return self.qualified_identifier == other.qualified_identifier
    
    def __repr__(self):
        return f'[{self.access_modifier.value} {self.definition_type.value} Symbol {self.qualified_identifier}]'


class ModuleSymbol(Symbol):
    def __init__(
        self: ModuleSymbol,
        location: Location,
        name: str,
        definition_type: DefinitionType,
        full_range: Range = None):
        super().__init__(location, SymbolIdentifier(name, SymbolType.MODULE), None, definition_type, full_range)

    def get_repository_identifier(self, root: Path) -> str:
        ' Returns the repository identifier (e.g.: smglom/repo) assuming this symbol is contained in <root>. '
        # root/<smglom/repo>/source/module.tex
        return list(self.location.path.relative_to(root).parents)[-3].as_posix()


class BindingSymbol(Symbol):
    def __init__(
        self: BindingSymbol,
        location: Location,
        lang: str,
        module: SymbolIdentifier,
        full_range: Range = None):
        super().__init__(
            location=location,
            identifier=SymbolIdentifier('_binding_', SymbolType.BINDING),
            parent=module,
            definition_type=DefinitionType.BINDING,
            full_range=full_range)
        self.lang = lang


class VerbSymbol(Symbol):
    def __init__(
        self: VerbSymbol,
        location: Location,
        name: str,
        module: SymbolIdentifier,
        definition_type: DefinitionType,
        noverb: bool = False,
        noverbs: Set[str] = None,
        full_range: Range = None):
        super().__init__(
            location=location,
            identifier=SymbolIdentifier(name, SymbolType.SYMBOL),
            parent=module,
            definition_type=definition_type,
            full_range=full_range)
        self.noverb = noverb
        self.noverbs = noverbs or set()

