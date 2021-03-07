from enum import Flag
from typing import List, Sequence, Tuple

import stexls
from stexls.util.format import format_enumeration
from .. import vscode

__all__ = ['ReferenceType', 'Reference']


class ReferenceType(Flag):
    """ The reference type is the expected type of the symbol pointed to by a reference.

    The statement used to generate the reference usually knows which types of symbols
    are expected. After the reference is resolved the symbol type and expected reference
    type can be compared in order to detect errors.
    """
    UNDEFINED = 0
    BINDING = 1
    MODULE = 1 << 1
    MODSIG = 1 << 2
    VIEWSIG = 1 << 3
    VIEWMOD = 1 << 4
    DEF = 1 << 5
    DREF = 1 << 6
    SYMDEF = 1 << 7
    SYM = 1 << 8
    ANY_DEFINITION = DEF | DREF | SYMDEF | SYM

    def contains_any_of(self, other) -> bool:
        """ Returns true if any reference types in "other" are contained in this.

        Example:
            >>> ReferenceType.ANY_DEFINITION.contains_any_of(ReferenceType.DREF|ReferenceType.SYM)
            True
            >>> ReferenceType.MODULE.contains_any_of(ReferenceType.MODULE)
            True
            >>> (ReferenceType.MODULE|ReferenceType.MODSIG).contains_any_of(ReferenceType.DEF|ReferenceType.SYMDEF)
            False
        """
        for exp in range(0, 1+other.value):
            mask = 1 << exp
            if mask > other.value:
                break
            if ReferenceType(other.value & mask) in self:
                return True
        return False

    def format_enum(self):
        """ Formats the flag as a list in case multiple are possible like: "module" or "modsig" for ReferenceType.MODULE|MODSIG

        Examples:
            >>> (ReferenceType.BINDING | ReferenceType.ANY_DEFINITION).format_enum()
            '"binding", "def", "dref", "symdef" or "sym"'
        """
        names: List[str] = []
        for exp in range(0, 1+self.value):
            mask = 1 << exp
            if mask > self.value:
                break
            if self.value & mask:
                names.append(ReferenceType(mask).name.lower())
        return format_enumeration(names, last='or')


class Reference:
    ' Container that contains information about which symbol is referenced by name. '

    def __init__(
            self,
            range: vscode.Range,
            scope: 'stexls.stex.symbols.Symbol',
            name: Sequence[str],
            reference_type: ReferenceType):
        """ Initializes the reference container.

        Parameters:
            range: Location at which the reference is created.
            scope: The parent symbol which contains range. Used to create error messages.
            name: Path to the symbol.
            reference_type: Expected type of the resolved symbol.
                Hint: The reference type can be or'd together to create more complex references.
        """
        assert range is not None
        assert name is not None
        assert all(isinstance(i, str) for i in name)
        self.range = range
        self.scope = scope
        self.name: Tuple[str, ...] = tuple(name)
        self.reference_type: ReferenceType = reference_type
        self.resolved_symbols: List['stexls.stex.symbols.Symbol'] = []

    def __repr__(self):
        return f'[Reference  "{"?".join(self.name)}" of type {self.reference_type.format_enum()} at {self.range.start.format()}]'
