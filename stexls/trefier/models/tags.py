from typing import Tuple
import numpy as np

__all__ = ['Tag']

class Tag:
    def __init__(self, label: np.ndarray, begin: int, stop: int, envs: Tuple[str, ...] = None):
        ''' Creates a tag with label and position information relative
            to the source text this tag originates from.
        Parameters:
            label: Some representation of the label.
            begin: Begin offset of the lexeme relative to the original text.
            stop: End offset of the lexeme relative to the original text.
            envs: Optional tuple of the environments the token is located inside of.
        '''
        self.label = label
        self.begin = begin
        self.stop = stop
        self.envs = envs

    def __repr__(self):
        return f'[Tag begin={self.begin} stop={self.stop} label={self.label}]'
