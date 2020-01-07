""" This file contains the equivalent to c++ object files, but for stex.
"""
from typing import List, Tuple
from stexls.util.location import Location
from stexls.util.latex.parser import LatexParser, Environment
from stexls.compiler.tags import Module, Binding, Trefi, Defi, Symi, Symdef, GImport

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
        self.modules: List[Module] = []
        self.bindings: List[Binding] = []
        self.trefis: List[Trefi] = []
        self.defis: List[Defi] = []
        self.syms: List[Symi] = []
        self.symdefs: List[Symdef] = []
        self.gimports: List[GImport] = []
        self.exceptions: List[Tuple[Location, ValueError]] = []
        self.syntax_errors = []
        def visitor(env: Environment):
            try:
                module = Module.from_environment(env)
                if module:
                    self.modules.append(module)
                    return
                binding = Binding.from_environment(env)
                if binding:
                    self.bindings.append(binding)
                    return
                trefi = Trefi.from_environment(env)
                if trefi:
                    self.trefis.append(trefi)
                    return
                defi = Defi.from_environment(env)
                if defi:
                    self.defis.append(defi)
                    return
                sym = Symi.from_environment(env)
                if sym:
                    self.syms.append(sym)
                    return
                symdef = Symdef.from_environment(env)
                if symdef:
                    self.symdefs.append(symdef)
                    return
                gimport = GImport.from_environment(env)
                if gimport:
                    self.gimports.append(gimport)
                    return
            except ValueError as e:
                self.exceptions.append((env.location, e))
                return

        parser = LatexParser(file)
        self.syntax_errors = parser.syntax_errors
        parser.walk(visitor)
