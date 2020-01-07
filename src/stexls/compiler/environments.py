from __future__ import annotations
from typing import Optional, Iterator, Tuple, List
import re
from stexls.util import roman_numerals
from stexls.util.latex.parser import Environment

class Module:
    PATTERN = re.compile(r'modsig')
    def __init__(self, name: str):
        self.name = name

    @classmethod
    def from_environment(self, e: Environment) -> Optional[Module]:
        match = Module.PATTERN.fullmatch(e.name)
        if not match:
            return
        assert len(e.rargs) == 1
        return Module(e.rargs[0].text_inside)


class Binding:
    PATTERN = re.compile(r'mhmodnl')
    def __init__(self, name: str, lang: str):
        self.name = name
        self.lang = lang

    @classmethod
    def from_environment(self, e: Environment) -> Optional[Binding]:
        match = Module.PATTERN.fullmatch(e.name)
        if not match:
            return
        assert len(e.rargs) == 2
        return Binding(
            e.rargs[0].text_inside,
            e.rargs[1].text_inside
        )


class Defi:
    PATTERN = re.compile(r'([ma]*)def([ivx]+)(s)?(\*)?')
    def __init__(
        self,
        tokens: List[str],
        options: str,
        m: bool,
        a: bool,
        i: int,
        s: bool,
        asterisk: bool):
        self.tokens = tokens
        self.options = options
        self.m = m
        self.a = a
        self.i = i
        self.s = s
        self.asterisk = asterisk

    @classmethod
    def from_environment(self, e: Environment) -> Optional[Defi]:
        match = Defi.PATTERN.fullmatch(e.name)
        if match is None:
            return None
        assert e.rargs
        assert len(e.oargs) <= 1
        return Defi(
            list(arg.text_inside for arg in e.rargs),
            ','.join(arg.text_inside for arg in e.oargs),
            'm' in match.group(1),
            'a' in match.group(1),
            roman_numerals.roman2int(match.group(2)),
            match.group(3) is not None,
            match.group(4) is not None)


class Trefi:
    PATTERN = re.compile(r'([ma]*)tref([ivx]+)(s)?(\*)?')
    def __init__(
        self,
        tokens: List[str],
        options: str,
        m: bool,
        a: bool,
        i: int,
        s: bool,
        asterisk: bool):
        self.tokens = tokens
        self.options = options
        self.m = m
        self.a = a
        self.i = i
        self.s = s
        self.asterisk = asterisk

    @classmethod
    def from_environment(self, e: Environment) -> Optional[Trefi]:
        match = Trefi.PATTERN.fullmatch(e.name)
        if match is None:
            return None
        assert e.rargs
        assert len(e.oargs) <= 1
        return Trefi(
            list(arg.text_inside for arg in e.rargs),
            ','.join(arg.text_inside for arg in e.oargs),
            'm' in match.group(1),
            'a' in match.group(1),
            roman_numerals.roman2int(match.group(2)),
            match.group(3) is not None,
            match.group(4) is not None,
        )


class Sym:
    PATTERN = re.compile(r'sym([ivx]+)(s)?(\*)?')
    def __init__(
        self,
        tokens: List[str],
        i: int,
        s: bool,
        asterisk: bool):
        self.i = i
        self.s = s
        self.asterisk = asterisk

    @classmethod
    def from_environment(self, e: Environment) -> Optional[Sym]:
        match = Sym.PATTERN.fullmatch(e.name)
        if match is None:
            return None
        assert len(e.rargs)
        return Sym(
            list(arg.text_inside for arg in e.rargs),
            roman_numerals.roman2int(match.group(1)),
            match.group(2) is not None,
            match.group(3) is not None,
        )


class Symdef:
    PATTERN = re.compile(r'symdef(\*)?')
    def __init__(self, asterisk: bool):
        self.asterisk = asterisk

    @staticmethod
    def from_environment(e: Environment) -> Optional[Symdef]:
        match = Symdef.PATTERN.fullmatch(e.name)
        if match is None:
            return None
        return Symdef(
            match.group(1) is not None,
        )


class GImport:
    PATTERN = re.compile(r'gimport(\*)?')
    def __init__(self, target: str, options: str, asterisk: bool):
        self.asterisk = asterisk

    @classmethod
    def from_environment(self, e: Environment) -> Optional[GImport]:
        match = GImport.PATTERN.fullmatch(e.name)
        if match is None:
            return None
        assert e.rargs
        assert len(e.oargs) <= 1
        return GImport(
            ','.join(arg.text_inside for arg in e.rargs),
            ','.join(arg.text_inside for arg in e.oargs),
            match.group(1) is not None,
        )


class GStructure:
    PATTERN = re.compile(r'gstructure(\*)?')
    def __init__(self, asterisk: bool):
        self.asterisk = asterisk

    @classmethod
    def from_environment(self, e: Environment) -> Optional[GStructure]:
        match = GStructure.PATTERN.fullmatch(e.name)
        if match is None:
            return None
