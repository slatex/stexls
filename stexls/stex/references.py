from typing import List, Sequence, Tuple

from .. import vscode
from . import symbols
from .reference_type import ReferenceType

__all__ = ['Reference']


class Reference:
    ' Container that contains information about which symbol is referenced by name. '

    def __init__(
            self,
            range: vscode.Range,
            scope: symbols.Symbol,
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
        self.resolved_symbols: List[symbols.Symbol] = []

    def __repr__(self):
        return f'[Reference  "{"?".join(self.name)}" of type {self.reference_type.format_enum()} at {self.range.start.format()}]'
