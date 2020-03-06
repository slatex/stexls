""" Linker for stex objects.
"""
from stexls.compiler.objects import StexObject
from stexls.compiler.symbols import Symbol
from stexls.util.location import Location

class Link:
    def __init__(self, symbol: Symbol, location: Location):
        """ Links the symbol with the location.
        The symbol contains its own location of definition and
        the link specifies a location to which the definition
        points to.

        Like a Tag in a tagfile.
        """
        self.symbol = symbol
        self.location = location

class Linker:
    def link(self, object: StexObject):
        pass

    def unlink(self, object: StexObject):
        pass