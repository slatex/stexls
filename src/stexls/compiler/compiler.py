"""A "compiler" for stex files.
"""
from stexls.util.latex.parser import LatexParser
from stexls.util.latex.parser import Token
import re

class Compiler:
    def __init__(self):
        pass

    def compile(self, file: str):
        """Compiles a file to an stex object file.

        Stex objects contain information about defined symbols,
        like modules and defis, about imports, and relocations
        like trefi, which require linking to be resolved.

        Args:
            file (str): Source file.
        """
        parser = LatexParser(file)
