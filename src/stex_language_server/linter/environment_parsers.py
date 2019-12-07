from __future__ import annotations
from typing import Optional, Iterator, Tuple
import re
from trefier.misc import roman_numerals


class DefData:
    PATTERN = re.compile(r'([ma]*)def([ivx]+)(s)?(\*)?')
    def __init__(self, m: bool, a: bool, i: int, s: bool, asterisk: bool):
        """ Data of 'defi' environment
        Arguments:
            :param m: m flag is a prefix.
            :param a: a flag is a prefix.
            :param i: Expected argument count.
            :param s: s flag at the end. 
            :param asterisk: If it is a * environment.
        """
        self.m = m
        self.a = a
        self.i = i
        self.s = s
        self.asterisk = asterisk

    @staticmethod
    def parse(env: str) -> Optional[DefData]:
        """ Parses the given latex environment name assuming it is a "defi." """
        match = DefData.PATTERN.fullmatch(env)
        if match is None:
            return None
        return DefData(
            'm' in match.group(1),
            'a' in match.group(1),
            roman_numerals.roman2int(match.group(2)),
            match.group(3) is not None,
            match.group(4) is not None)


class TrefData:
    PATTERN = re.compile(r'([ma]*)tref([ivx]+)(s)?(\*)?')
    def __init__(self, m: bool, a: bool, i: int, s: bool, asterisk: bool):
        """ Data of 'trefi' environment
        Arguments:
            :param m: m flag is a prefix.
            :param a: a flag is a prefix.
            :param i: Expected argument count.
            :param s: s flag at the end. 
            :param asterisk: If it is a * environment.
        """
        self.m = m
        self.a = a
        self.i = i
        self.s = s
        self.asterisk = asterisk

    @staticmethod
    def parse(env: str) -> Optional[TrefData]:
        """ Parses the given latex environment name assuming it is a "trefi." """
        match = TrefData.PATTERN.fullmatch(env)
        if match is None:
            return None
        return TrefData(
            'm' in match.group(1),
            'a' in match.group(1),
            roman_numerals.roman2int(match.group(2)),
            match.group(3) is not None,
            match.group(4) is not None,
        )


class SymData:
    PATTERN = re.compile(r'sym([ivx]+)(s)?(\*)?')
    def __init__(self, i: int, s: bool, asterisk: bool):
        """ Data of 'sym' environment
        Arguments:
            :param i: Expected argument count.
            :param s: s flag at the end. 
            :param asterisk: If it is a * environment.
        """
        self.i = i
        self.s = s
        self.asterisk = asterisk

    @staticmethod
    def parse(env: str) -> Optional[SymData]:
        """ Parses the given latex environment name assuming it is a "sym." """
        match = SymData.PATTERN.fullmatch(env)
        if match is None:
            return None
        return SymData(
            roman_numerals.roman2int(match.group(1)),
            match.group(2) is not None,
            match.group(3) is not None,
        )


class SymdefData:
    PATTERN = re.compile(r'symdef(\*)?')
    def __init__(self, asterisk: bool):
        """ Data of 'symdef' environment
        Arguments:
            :param asterisk: If it is a * environment.
        """
        self.asterisk = asterisk

    @staticmethod
    def parse(env: str) -> Optional[SymdefData]:
        """ Parses the given latex environment name assuming it is a "symdef." """
        match = SymdefData.PATTERN.fullmatch(env)
        if match is None:
            return None
        return SymdefData(
            match.group(1) is not None,
        )


class GImportData:
    PATTERN = re.compile(r'gimport(\*)?')
    def __init__(self, asterisk: bool):
        """ Data of 'gimport' environment
        Arguments:
            :param asterisk: If it is a * environment.
        """
        self.asterisk = asterisk

    @staticmethod
    def parse(env: str) -> Optional[GImportData]:
        """ Parses the given latex environment name assuming it is a "gimport." """
        match = GImportData.PATTERN.fullmatch(env)
        if match is None:
            return None
        return GImportData(
            match.group(1) is not None,
        )


class GStructureData:
    PATTERN = re.compile(r'gstructure(\*)?')
    def __init__(self, asterisk: bool):
        """ Data of 'gstructure' environment
        Arguments:
            :param asterisk: If it is a * environment.
        """
        self.asterisk = asterisk

    @staticmethod
    def parse(env: str) -> Optional[GStructureData]:
        """ Parses the given latex environment name assuming it is a "gstructure." """
        match = GStructureData.PATTERN.fullmatch(env)
        if match is None:
            return None
        return GStructureData(
            match.group(1) is not None,
        )


class OArgData:
    PATTERN=re.compile(r'(?<=,|\[)(?:(\w+)=)?([^,\]]*)')
    def __init__(self,
        name: Optional[str],
        name_span: Optional[Tuple[int, int]],
        value: str,
        value_span: Tuple[int, int]):
        """ Contains data about an OArg of a latex environment.
        if name is not None then the argument was [...,"<name>=<value>",...]
        else it was [...,<value>,...].

        Arguments:
            :param name: Optional name of the argument.
            :param name_span: Start and stop index of the argument name string relative to the given string. None if name is None.
            :param value: Value of the argument.
            :param value_span: Start and stop index of the argument value string relative to the given string.
        """
        self.name = name
        self.name_span = name_span
        self.value = value
        self.value_span = value_span

    @staticmethod
    def parse(env_oargs: str) -> Iterator[OArgData]:
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
