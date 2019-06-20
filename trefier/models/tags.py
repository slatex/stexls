from trefier.misc.location import *

__all__ = ['Tag']

class Tag:
    def __init__(self, token_range: Range):
        self.token_range = token_range
