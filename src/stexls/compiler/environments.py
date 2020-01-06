from __future__ import annotations
from typing import Optional, Iterator, Tuple
import re
from stexls.util import roman_numerals


class Defi:
    PATTERN = re.compile(r'([ma]*)def([ivx]+)(s)?(\*)?')
    def __init__(self, m: bool, a: bool, i: int, s: bool, asterisk: bool):
        """ Data of 'defi' environment.

        Args:
            m (bool): m flag is a prefix.
            a (bool): a flag is a prefix.
            i (int): Expected argument count.
            s (bool): s flag at the end.
            asterisk (bool): If it is a * environment.
        """
        self.m = m
        self.a = a
        self.i = i
        self.s = s
        self.asterisk = asterisk

    @staticmethod
    def from_string(env: str) -> Optional[Defi]:
        """ Parses the given latex environment name assuming it is a "defi." """
        match = Defi.PATTERN.fullmatch(env)
        if match is None:
            return None
        return Defi(
            'm' in match.group(1),
            'a' in match.group(1),
            roman_numerals.roman2int(match.group(2)),
            match.group(3) is not None,
            match.group(4) is not None)


class Trefi:
    PATTERN = re.compile(r'([ma]*)tref([ivx]+)(s)?(\*)?')
    def __init__(self, m: bool, a: bool, i: int, s: bool, asterisk: bool):
        """ Data of 'trefi' environment

        Args:
            m (bool): m flag is a prefix.
            a (bool): a flag is a prefix.
            i (int): Expected argument count.
            s (bool): s flag at the end.
            asterisk (bool): If it is a * environment.
        """
        self.m = m
        self.a = a
        self.i = i
        self.s = s
        self.asterisk = asterisk

    @staticmethod
    def from_string(env: str) -> Optional[Trefi]:
        """ Parses the given latex environment name assuming it is a "trefi." """
        match = Trefi.PATTERN.fullmatch(env)
        if match is None:
            return None
        return Trefi(
            'm' in match.group(1),
            'a' in match.group(1),
            roman_numerals.roman2int(match.group(2)),
            match.group(3) is not None,
            match.group(4) is not None,
        )


class Sym:
    PATTERN = re.compile(r'sym([ivx]+)(s)?(\*)?')
    def __init__(self, i: int, s: bool, asterisk: bool):
        """ Data of 'sym' environment

        Args:
            i (int): Expected argument count.
            s (bool): s flag at the end.
            asterisk (bool): If it is a * environment.
        """
        self.i = i
        self.s = s
        self.asterisk = asterisk

    @staticmethod
    def from_string(env: str) -> Optional[Sym]:
        """ Parses the given latex environment name assuming it is a "sym." """
        match = Sym.PATTERN.fullmatch(env)
        if match is None:
            return None
        return Sym(
            roman_numerals.roman2int(match.group(1)),
            match.group(2) is not None,
            match.group(3) is not None,
        )


class Symdef:
    PATTERN = re.compile(r'symdef(\*)?')
    def __init__(self, asterisk: bool):
        """ Data of 'symdef' environment

        Args:
            asterisk (bool): If it is a * environment.
        """
        self.asterisk = asterisk

    @staticmethod
    def from_string(env: str) -> Optional[Symdef]:
        """ Parses the given latex environment name assuming it is a "symdef." """
        match = Symdef.PATTERN.fullmatch(env)
        if match is None:
            return None
        return Symdef(
            match.group(1) is not None,
        )


class GImport:
    PATTERN = re.compile(r'gimport(\*)?')
    def __init__(self, asterisk: bool):
        """ Data of 'gimport' environment

        Args:
            asterisk (bool): If it is a * environment.
        """
        self.asterisk = asterisk

    @staticmethod
    def from_string(env: str) -> Optional[GImport]:
        """ Parses the given latex environment name assuming it is a "gimport." """
        match = GImport.PATTERN.fullmatch(env)
        if match is None:
            return None
        return GImport(
            match.group(1) is not None,
        )


class GStructure:
    PATTERN = re.compile(r'gstructure(\*)?')
    def __init__(self, asterisk: bool):
        """ Data of 'gstructure' environment

        Args:
            asterisk (bool): If it is a * environment.
        """
        self.asterisk = asterisk

    @staticmethod
    def from_string(env: str) -> Optional[GStructure]:
        """ Parses the given latex environment name assuming it is a "gstructure." """
        match = GStructure.PATTERN.fullmatch(env)
        if match is None:
            return None
        return GStructure(
            match.group(1) is not None,
        )


class OArgData:
    PATTERN=re.compile(r'(?<=,|\[)(?:\s*(\S+)\s*=)?([^,\]]*)')
    def __init__(self,
        name: Optional[str],
        name_span: Optional[Tuple[int, int]],
        value: str,
        value_span: Tuple[int, int]):
        """ Contains data about an OArg of a latex environment.
        if name is not None then the argument was [...,"<name>=<value>",...]
        else it was [...,<value>,...].

        Args:
            name (str): Optional name of the argument.
            name_span (Tuple[int, int]): Start and stop index of the argument name string relative to the given string. None if name is None.
            value (str): Value of the argument.
            value_span (Tuple[int, int]): Start and stop index of the argument value string relative to the given string.
        """
        self.name = name
        self.name_span = name_span
        self.value = value
        self.value_span = value_span

    @staticmethod
    def from_string(env_oargs: str) -> Iterator[OArgData]:
        """ Parses a latex environment's o argument string and returns
            all o arguments inside it. """
        if not env_oargs:
            return []
        if (env_oargs[0], env_oargs[-1]) != ('[', ']'):
            raise Exception('Given oargs string is invalid because it doesn\'t start with "[" and ends with "]."')
        for match in OArgData.PATTERN.finditer(env_oargs):
            name = match.group(1)
            name_start = 0 if name is None else match.span()[0]
            name_stop = 0 if name is None else name_start + len(name)
            value = match.group(2)
            value_start = 0 if name is None else name_stop + 1
            value_stop = match.span()[-1]
            yield OArgData(
                    name=name,
                    name_span=None if name is None else (name_start, name_stop),
                    value=value,
                    value_span=(value_start, value_stop))
