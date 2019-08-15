from __future__ import annotations
import numpy as np
from trefier.misc.location import Range

__all__ = ['Tag']


class Tag:
    def __init__(self, label: np.ndarray, token_range: Range, lexeme: str):
        self.label = label
        self.token_range = token_range
        self.lexeme = lexeme
    
    def __repr__(self):
        return f'{self.lexeme}:{self.label.round(2)}'
