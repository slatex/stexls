""" This file contains the equivalent to c++ object files, but for stex.
"""
from typing import List, Tuple, Optional
from stexls.util.location import Location, Range, Position
from stexls.util.latex.parser import LatexParser, Environment
from stexls.compiler.symbols import *

class StexObject:
    """ An object contains information about symbols, locations, imports
    of an stex source file.
    """
    def __init__(self, file: str):
        """Compiles a file to an stex object file.

        Stex objects contain information about defined symbols,
        like modules and defis, about imports, and relocations
        like trefi, which require linking to be resolved.

        Args:
            file (str): Source file.
        """
        self.file = file
        self.modsigs: List[ModsigSymbol] = []
        self.mhmodnls: List[MhmodnlSymbol] = []
        self.trefis: List[TrefiSymbol] = []
        self.defis: List[DefiSymbol] = []
        self.syms: List[SymiSymbol] = []
        self.symdefs: List[SymdefSymbol] = []
        self.gimports: List[GImportSymbol] = []
        self.exceptions: List[Tuple[Location, ValueError]] = []
        self.syntax_errors = []
        self.success = False
        def visitor(env: Environment):
            try:
                module = ModsigSymbol.from_environment(env)
                if module:
                    self.modsigs.append(module)
                    return
                binding = MhmodnlSymbol.from_environment(env)
                if binding:
                    self.mhmodnls.append(binding)
                    return
                trefi = TrefiSymbol.from_environment(env)
                if trefi:
                    self.trefis.append(trefi)
                    return
                defi = DefiSymbol.from_environment(env)
                if defi:
                    self.defis.append(defi)
                    return
                sym = SymiSymbol.from_environment(env)
                if sym:
                    self.syms.append(sym)
                    return
                symdef = SymdefSymbol.from_environment(env)
                if symdef:
                    self.symdefs.append(symdef)
                    return
                gimport = GImportSymbol.from_environment(env)
                if gimport:
                    self.gimports.append(gimport)
                    return
            except ValueError as e:
                self.exceptions.append((env.location, e))
                return
        try:
            parser = LatexParser(file)
            self.syntax_errors = parser.syntax_errors
            parser.walk(visitor)
            self.success = True
        except Exception as e:
            try:
                with open(file) as f:
                    lines = f.readlines()
            except:
                lines = []
            last_line = len(lines)
            last_character = len(lines[-1]) if lines else 0
            self.exceptions.append((Location(file, Range(Position(0, 0), Position(last_line, last_character))), e))
