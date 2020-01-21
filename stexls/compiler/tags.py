from __future__ import annotations
from typing import Optional, Iterator, Tuple, List
import re
from stexls.util import roman_numerals
from stexls.util.location import Location, Range, Position
from stexls.util.latex.parser import Environment, Node


class TagToken:
    def __init__(self, value: str, range: Range):
        self.value = value
        self.range = range

    def __repr__(self):
        return self.value

    @staticmethod
    def from_node(node: Node) -> TagToken:
        return TagToken(node.text_inside, node.location.range)

    @staticmethod
    def from_node_union(nodes: List[Node], separator: str = ',') -> Optional[TagToken]:
        if not nodes:
            return
        tags = map(TagToken.from_node, nodes)
        values, ranges = zip(*((tok.value, tok.range) for tok in tags))
        return TagToken(separator.join(values), Range.big_union(ranges))


class Tag:
    def __init__(self, location: Location):
        self.location = location


class Module(Tag):
    PATTERN = re.compile(r'modsig')
    def __init__(self, location: Location, name: TagToken):
        super().__init__(location)
        self.name = name

    @classmethod
    def from_environment(self, e: Environment) -> Optional[Module]:
        match = Module.PATTERN.fullmatch(e.env_name)
        if not match:
            return
        if len(e.rargs) != 1:
            raise ValueError(f'RArg count mismatch (expected 1, found {len(e.rargs)}).')
        return Module(e.location, TagToken.from_node(e.rargs[0]))

    def __repr__(self):
        return f'[module name={self.name}]'


class Binding(Tag):
    PATTERN = re.compile(r'mhmodnl')
    def __init__(self, location: Location, name: TagToken, lang: TagToken):
        super().__init__(location)
        self.name = name
        self.lang = lang

    @classmethod
    def from_environment(self, e: Environment) -> Optional[Binding]:
        match = Binding.PATTERN.fullmatch(e.env_name)
        if not match:
            return
        if len(e.rargs) != 2:
            raise ValueError(f'RArg count mismatch (expected 2, found {len(e.rargs)}).')
        return Binding(
            e.location,
            TagToken.from_node(e.rargs[0]),
            TagToken.from_node(e.rargs[1])
        )

    def __repr__(self):
        return f'[binding name={self.name} lang={self.lang}]'


class Defi(Tag):
    PATTERN = re.compile(r'([ma]*)def([ivx]+)(s)?(\*)?')
    def __init__(
        self,
        location: Location,
        tokens: List[TagToken],
        options: Optional[TagToken],
        m: bool,
        a: bool,
        i: int,
        s: bool,
        asterisk: bool):
        super().__init__(location)
        self.tokens = tokens
        self.options = options
        self.m = m
        self.a = a
        self.i = i
        self.s = s
        self.asterisk = asterisk

    @classmethod
    def from_environment(self, e: Environment) -> Optional[Defi]:
        match = Defi.PATTERN.fullmatch(e.env_name)
        if match is None:
            return None
        if not e.rargs:
            raise ValueError('RArg count mismatch (expected at least 1, found 0).')
        if len(e.oargs) > 1:
            raise ValueError(f'OArg count mismatch (expected at most 1, found {len(e.oargs)})')
        return Defi(
            e.location,
            list(map(TagToken.from_node, e.rargs)),
            TagToken.from_node_union(e.oargs),
            'm' in match.group(1),
            'a' in match.group(1),
            roman_numerals.roman2int(match.group(2)),
            match.group(3) is not None,
            match.group(4) is not None)

    def __repr__(self):
        return f'[defi options="{self.options}" tokens={self.tokens}]'


class Trefi(Tag):
    PATTERN = re.compile(r'([ma]*)tref([ivx]+)(s)?(\*)?')
    def __init__(
        self,
        location: Location,
        tokens: List[TagToken],
        options: Optional[TagToken],
        m: bool,
        a: bool,
        i: int,
        s: bool,
        asterisk: bool):
        super().__init__(location)
        self.tokens = tokens
        self.options = options
        self.m = m
        self.a = a
        self.i = i
        self.s = s
        self.asterisk = asterisk

    @classmethod
    def from_environment(self, e: Environment) -> Optional[Trefi]:
        match = Trefi.PATTERN.fullmatch(e.env_name)
        if match is None:
            return None
        if not e.rargs:
            raise ValueError('RArg count mismatch (expected at least 1, found 0).')
        if len(e.oargs) > 1:
            raise ValueError(f'OArg count mismatch (expected at most 1, found {len(e.oargs)})')
        return Trefi(
            e.location,
            list(map(TagToken.from_node, e.rargs)),
            TagToken.from_node_union(e.oargs),
            'm' in match.group(1),
            'a' in match.group(1),
            roman_numerals.roman2int(match.group(2)),
            match.group(3) is not None,
            match.group(4) is not None,
        )

    def __repr__(self):
        return f'[trefi options="{self.options}" tokens={self.tokens}]'


class Symi(Tag):
    PATTERN = re.compile(r'sym([ivx]+)(s)?(\*)?')
    def __init__(
        self,
        location: Location,
        tokens: List[TagToken],
        i: int,
        s: bool,
        asterisk: bool):
        super().__init__(location)
        self.tokens = tokens
        self.i = i
        self.s = s
        self.asterisk = asterisk

    @classmethod
    def from_environment(self, e: Environment) -> Optional[Symi]:
        match = Symi.PATTERN.fullmatch(e.env_name)
        if match is None:
            return None
        if not e.rargs:
            raise ValueError('RArg count mismatch (expected at least 1, found 0).')
        return Symi(
            e.location,
            list(map(TagToken.from_node, e.rargs)),
            roman_numerals.roman2int(match.group(1)),
            match.group(2) is not None,
            match.group(3) is not None,
        )

    def __repr__(self):
        return f'[sym{"*"*self.asterisk} i={self.i} s={self.s} tokens={self.tokens}]'


class Symdef(Tag):
    PATTERN = re.compile(r'symdef(\*)?')
    def __init__(self, location: Location, tokens: List[TagToken], options: Optional[TagToken], asterisk: bool):
        super().__init__(location)
        self.tokens = tokens
        self.options = options
        self.asterisk = asterisk

    @staticmethod
    def from_environment(e: Environment) -> Optional[Symdef]:
        match = Symdef.PATTERN.fullmatch(e.env_name)
        if match is None:
            return None
        if not e.oargs:
            raise ValueError('RArg count mismatch (expected at least 1, found 0).')
        return Symdef(
            e.location,
            list(map(TagToken.from_node, e.rargs)),
            TagToken.from_node_union(e.oargs),
            match.group(1) is not None,
        )

    def __repr__(self):
        return f'[symdef{"*"*self.asterisk} options="{self.options}" tokens={self.tokens}]'


class GImport(Tag):
    PATTERN = re.compile(r'gimport(\*)?')
    def __init__(self, location: Location, target: TagToken, options: Optional[TagToken], asterisk: bool):
        super().__init__(location)
        self.target = target
        self.options = options
        self.asterisk = asterisk

    @classmethod
    def from_environment(self, e: Environment) -> Optional[GImport]:
        match = GImport.PATTERN.fullmatch(e.env_name)
        if match is None:
            return None
        if not e.rargs:
            raise ValueError('RArg count mismatch (expected at least 1, found 0).')
        if len(e.oargs) > 1:
            raise ValueError(f'OArg count mismatch (expected at most 1, found {len(e.oargs)})')
        return GImport(
            e.location,
            TagToken.from_node_union(e.rargs),
            TagToken.from_node_union(e.oargs),
            match.group(1) is not None,
        )

    def __repr__(self):
        return f'[gimport{"*"*self.asterisk} options="{self.options}" target={self.target}]'


class GStructure(Tag):
    PATTERN = re.compile(r'gstructure(\*)?')
    def __init__(self, location: Location, asterisk: bool):
        super().__init__(location)
        self.asterisk = asterisk

    @classmethod
    def from_environment(self, e: Environment) -> Optional[GStructure]:
        match = GStructure.PATTERN.fullmatch(e.env_name)
        if match is None:
            return None
