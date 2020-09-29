from __future__ import annotations
import os
from typing import Set, Optional, Dict, List, Union, Tuple, Iterator
from enum import Enum, Flag
from pathlib import Path
from stexls.vscode import Location, Range, DocumentSymbol, Position
from stexls.stex.exceptions import DuplicateSymbolDefinedException, InvalidSymbolRedifinitionException
from stexls.util.format import format_enumeration


__all__ = [
    'AccessModifier',
    'ModuleType',
    'DefType',
    'Symbol',
    'ModuleSymbol',
    'BindingSymbol',
    'DefSymbol',
    'RootSymbol',
    'ScopeSymbol',
]


class AccessModifier(Flag):
    PUBLIC=0
    PROTECTED=1
    PRIVATE=3


class ModuleType(Enum):
    ' For module symbols: Used to remember which latex environment created this module. '
    MODSIG='modsig'
    MODULE='module'


class DefType(Enum):
    ' For definitions: Used to remember which latex environment created this module (e.g.: defii{}, symii{}, symdef{} or drefi{}) '
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
        assert location is not None, "Invalid symbol location"
        assert isinstance(name, str), "Member 'name' is not of type str"
        self.name = name
        self.parent: Optional[Symbol] = None
        self.children: Dict[str, List[Symbol]] = dict()
        self.location = location
        self.access_modifier: AccessModifier = AccessModifier.PUBLIC

    def import_from(self, module: Symbol):
        ' Imports the symbols from <source> into this symbol table. '
        cpy = module.shallow_copy()
        try:
            self.add_child(cpy)
        except (InvalidSymbolRedifinitionException, DuplicateSymbolDefinedException):
            # TODO: Currently already imported modules are ignored, what's the right procedure here?
            # TODO: Propagate import error, but probably not useful here
            # TODO: Solution: Report Indirect import errors.
            return
        for alts in module.children.values():
            # TODO: Import behaviour of 'import scopes' like 'frame' and 'omtext' --> What to do with defis inside these?
            for child in alts:
                if child.access_modifier != AccessModifier.PUBLIC:
                    continue
                if isinstance(child, ModuleSymbol):
                    self.import_from(child)
                elif isinstance(child, DefSymbol):
                    # TODO: Correct add_child behaviour depending on the context the symbol was imported under
                    try:
                        cpy.add_child(child.shallow_copy(), len(alts) > 1)
                    except (InvalidSymbolRedifinitionException, DuplicateSymbolDefinedException):
                        # TODO: What to do in case of error? Should this be impossible?
                        pass

    def get_visible_access_modifier(self) -> AccessModifier:
        ' Gets the access modifier visible from the symbol tree root. '
        if self.parent and self.access_modifier != AccessModifier.PRIVATE:
            return self.parent.get_visible_access_modifier() | self.access_modifier
        return self.access_modifier

    def __iter__(self) -> Iterator[Symbol]:
        ' Iterates over all child symbols. '
        # TODO: Remove this because its unsafe -> Add explicit .flat() method
        for alts in self.children.values():
            for child in alts:
                yield child
                yield from child

    def is_parent_of(self, other: Symbol) -> bool:
        ' Returns true if this symbol is a parent of the other symbol. '
        parent = other.parent
        while parent is not None:
            if self == parent:
                return True
            parent = parent.parent
        return False

    def shallow_copy(self) -> Symbol:
        ' Creates a shallow copy of this symbol and it\'s parameterization. Does not create a copy of the symbol table! '
        raise NotImplementedError

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
        ' Find the first parent BindingSymbol. '
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
        if child.name in self.children:
            if not alternative:
                raise DuplicateSymbolDefinedException(f'Symbol with name "{child.name}" already added: {self.location.format_link()}')
            for prev_child in self.children[child.name]:
                if not isinstance(prev_child, type(child)):
                    raise InvalidSymbolRedifinitionException(f'Symbol types do not match to previous definition: {type(child)} vs. {type(prev_child)}')
                if isinstance(child, DefSymbol):
                    if child.def_type != prev_child.def_type:
                        raise InvalidSymbolRedifinitionException(f'Redefinition definition types do not match: {child.def_type} vs. {prev_child.def_type}')
                    if child.noverb != prev_child.noverb:
                        a = 'noverb' if child.noverb else 'not noverb'
                        b = 'noverb' if prev_child.noverb else 'not noverb'
                        raise InvalidSymbolRedifinitionException(f'Redefinition noverb signatures do not match to previous definition: {a} vs. {b}')
                    if len(child.noverbs) != len(prev_child.noverbs) or not all(a==b for a, b in zip(child.noverbs, prev_child.noverbs)):
                        a = format_enumeration(child.noverbs, last='and')
                        b = format_enumeration(prev_child.noverbs, last='and')
                        raise InvalidSymbolRedifinitionException(f'Redefinition noverb signatures do not match to previous definition: {a} vs. {b}')
        child.parent = self
        self.children.setdefault(child.name, []).append(child)

    def lookup(self, identifier: Union[str, List[str]]) -> List[Symbol]:
        """ Symbol lookup searches for symbols with a given identifier.
        A "lookup" is search operation that can change the root to a parent.
        After a root has been found, the normal "find" operation will take over and only
        look through a child sub-tree.

        Parameters:
            identifier: Symbol identifier.

        Returns:
            All symbols with the specified id.
        """
        # Force id to be a list
        if isinstance(identifier, str):
            identifier = [identifier]
        # Find the other identifiers in the subbranches of the children
        resolved_symbols = [
            symbol
            # Lookup the root identifier
            for resolved_root in self.children.get(identifier[0], [])
            # Resolve the rest of the identifier
            for symbol in resolved_root.find(identifier[1:])
        ]
        # If nothing was resolved yet, try to search for the first symbol inside the parents
        if not resolved_symbols:
            # Lookup the identifier in parent tree
            if self.parent and not isinstance(self, (ModuleSymbol, BindingSymbol)):
                # TODO: Is preventing lookup through modules enough? Or is there a more generic way to describe this lookup behaviour?
                return self.parent.lookup(identifier)
            # This is a failsafe in case the current module is referenced inside itself
            # This is needed because else referencing another module inside the same file might be possible
            # depending on the order of declaration, but not allowed!
            # This also must be the last check else referencing nested symbols with the same name is impossible
            if self.name == identifier[0]:
                return self.find(identifier[1:])
        return resolved_symbols

    def find(self, identifier: Union[str, List[str]]) -> List[Symbol]:
        """ Searches the identified symbol in sub-trees of this symbols' children.

        Parameters:
            identifier: Identifier of the child symbol.

        Returns:
            All symbols with the specified identifier.
        """
        if not identifier:
            return [self]
        if isinstance(identifier, str):
            identifier = [identifier]
        children = self.children.get(identifier[0], [])
        if len(identifier) > 1:
            return [
                resolved
                for child in children
                for resolved in child.find(identifier[1:])
            ]
        return children

    def __repr__(self):
        return f'[{self.access_modifier.name} Symbol {self.name}]'


class ModuleSymbol(Symbol):
    UNNAMED_MODULE_COUNT=0
    def __init__(
        self,
        module_type: ModuleType,
        location: Location,
        name: str = None):
        """ New module signature symbol.

        Parameters:
            module_type: The latex environment type used to define this symbol.
            location: Location at which the module symbol is created.
            name: Name of the module. If no name is provided, a name will be atomatically created.
        """
        super().__init__(location, name or f'__MODULESYMBOL#{ModuleSymbol.UNNAMED_MODULE_COUNT}__')
        if not name:
            ModuleSymbol.UNNAMED_MODULE_COUNT += 1
            self.access_modifier = AccessModifier.PRIVATE
        self.module_type = module_type

    def shallow_copy(self) -> ModuleSymbol:
        cpy = ModuleSymbol(self.module_type, self.location.copy(), self.name)
        cpy.access_modifier = self.access_modifier
        return cpy

    def get_current_module(self) -> ModuleSymbol:
        return self

    def __repr__(self):
        return f'[{self.access_modifier.name} ModuleSymbol "{self.name}"/{self.module_type.name} at {self.location.range.start.format()}]'


class DefSymbol(Symbol):
    def __init__(
        self,
        def_type: DefType,
        location: Location,
        name: str,
        noverb: bool = False,
        noverbs: Set[str] = None,
        access_modifier: AccessModifier = AccessModifier.PUBLIC):
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
        self.access_modifier = access_modifier

    def __repr__(self):
        return f'[{self.access_modifier.name} DefSymbol "{self.name}"/{self.def_type.name} at {self.location.range.start.format()}]'

    def shallow_copy(self) -> DefSymbol:
        cpy = DefSymbol(self.def_type, self.location.copy(), self.name, self.noverb, self.noverbs.copy())
        cpy.access_modifier = self.access_modifier
        return cpy


class BindingSymbol(Symbol):
    def __init__(self, location: Location, module: str, lang: str):
        super().__init__(location, module)
        self.lang = lang

    def get_current_binding(self) -> BindingSymbol:
        return self

    def shallow_copy(self) -> BindingSymbol:
        cpy = BindingSymbol(self.location.copy(), self.name, self.lang)
        cpy.access_modifier = self.access_modifier
        return cpy

    def __repr__(self):
        return f'[{self.access_modifier.name} BindingSymbol {self.name}.{self.lang} at {self.location.range.start.format()}]'

class RootSymbol(Symbol):
    NAME = '__root__'
    def __init__(self, location: Location):
        super().__init__(location, RootSymbol.NAME)

    @property
    def qualified(self) -> List[str]:
        return ()

    def shallow_copy(self):
        raise ValueError('Root symbols should never be copied, but created explicitly!')

class ScopeSymbol(Symbol):
    COUNTER=0
    def __init__(self, location: Location, name: str = 'UNNAMED_SCOPE'):
        super().__init__(location, f'__{name}#{ScopeSymbol.COUNTER}__')
        ScopeSymbol.COUNTER += 1
        self._name = name
        self.access_modifier = AccessModifier.PRIVATE

    def __repr__(self):
        return f'[{self.access_modifier.name} Scope "{self.name}" at {self.location.range.start.format()}]'

    def shallow_copy(self) -> ScopeSymbol:
        cpy = ScopeSymbol(self.location.copy(), name=self._name)
        cpy.access_modifier = self.access_modifier
        return cpy
