from __future__ import annotations

from typing import List, Optional, Sequence, Tuple, Union

from .. import vscode
from . import symbols
from .dependency import Dependency
from .reference_type import ReferenceType

__all__ = ['Reference']


class Reference:
    ' Container that contains information about which symbol is referenced by name. '

    def __init__(
            self,
            range: vscode.Range,
            scope: symbols.Symbol,
            name: Sequence[str],
            reference_type: ReferenceType,
            parent: Optional[Union[Reference, Dependency]] = None):
        """ Initializes the reference container.

        Parameters:
            range: Location at which the reference is created.
            scope: The parent symbol which contains range. Used to create error messages.
            name: Path to the symbol.
            reference_type: Expected type of the resolved symbol.
                Hint: The reference type can be or'd together to create more complex references.
            parent (Reference, optional): An optional `parent` reference.
                The parent reference is a reference that needs to be able to resolve before
                this reference will be able to resolve.
                Used to suppress errors of this reference if the parent reference is not resolved.
        """
        assert range is not None
        assert name is not None
        assert all(isinstance(i, str) for i in name)
        self.range = range
        self.scope = scope
        self.name: Tuple[str, ...] = tuple(name)
        self.reference_type: ReferenceType = reference_type
        self.resolved_symbols: List[symbols.Symbol] = []
        self.parent = parent

    def __repr__(self):
        return f'[Reference  "{"?".join(self.name)}" of type {self.reference_type.format_enum()} at {self.range.start.format()}]'
