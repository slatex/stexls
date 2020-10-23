from typing import Tuple
import numpy as np
from stexls.util.latex.tokenizer import LatexToken


__all__ = ['Tag']

class Tag:
    def __init__(self, label: np.ndarray, token: LatexToken):
        ''' Creates a tag with label and position information relative
            to the source text this tag originates from.

        Parameters:
            label: Some representation of the label.
            token: Source token.
        '''
        self.label = label
        self.token = token

    def __repr__(self):
        return f'[Tag {self.label} of {self.token}]'
