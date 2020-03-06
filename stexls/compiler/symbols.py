from __future__ import annotations
from typing import Optional, Iterator, Tuple, List
import re
from stexls.util import roman_numerals
from stexls.util.location import Location, Range, Position
from stexls.util.latex.parser import Environment, Node

__all__ = [
    'TokenWithLocation',
    'Symbol',
    'ModsigSymbol',
    'MhmodnlSymbol',
    'TrefiSymbol',
    'DefiSymbol',
    'SymiSymbol',
    'SymdefSymbol',
    'GImportSymbol',
    'GUseSymbol',
    'GStructureSymbol',
]

class TokenWithLocation:
    def __init__(self, value: str, range: Range):
        self.value = value
        self.range = range
    
    def as_options(self) -> Tuple[Tuple[List[str], Dict[str, str]], Tuple[List[Range], Dict[str, Range]]]:
        """ Parses the value attribute as a comma seperated
        list of options which are either named and prefixed
        with "<name>=" or unnamed.

        E.g.: "named1=value1,unnamed,named2=value2,unnamed2"

        Returns:
            The string is parsed as a tuple of a list of the
            unnamed options "[unnamed,unnamed2]", in this case.
            And as a dictionary of named options:
            {"named1":"value1","named2":"value2"}
            Additionally returns a tuple of a list of ranges for the
            unnamed values and a dict from name to named value ranges.

        Examples:
            >>> token = TokenWithLocation('name=value,1', Range(Position(1, 1), Position(1, 13)))
            >>> values, ranges = token.as_options()
            >>> values
            (['1'], {'name': 'value'})
            >>> ranges
            ([[Range (1 12) (1 13)]], {'name': [Range (1 6) (1 11)]})
        """
        unnamed: List[str] = []
        unnamed_ranges: List[Range] = []
        named: Dict[str, str] = {}
        named_ranges: Dict[str, Range] = {}
        offset = 0
        for part in self.value.split(','):
            if '=' in part:
                name, value = part.split('=', 1)
                named[name.strip()] = value.strip()
                new_start = self.range.start.translate(
                    characters=offset + len(name) + 1)
                new_end = new_start.translate(
                    characters=len(value))
                named_ranges[name.strip()] = Range(new_start, new_end)
            else:
                unnamed.append(part.strip())
                new_start = self.range.start.translate(
                    characters=offset)
                new_end = new_start.translate(
                    characters=len(part))
                unnamed_ranges.append(Range(new_start, new_end))
            offset += len(part) + 1
        return (unnamed, named), (unnamed_ranges, named_ranges)


    def __repr__(self):
        return self.value

    @staticmethod
    def from_node(node: Node) -> TokenWithLocation:
        return TokenWithLocation(node.text_inside, node.location.range)

    @staticmethod
    def from_node_union(nodes: List[Node], separator: str = ',') -> Optional[TokenWithLocation]:
        if not nodes:
            return
        tags = map(TokenWithLocation.from_node, nodes)
        values, ranges = zip(*((tok.value, tok.range) for tok in tags))
        return TokenWithLocation(separator.join(values), Range.big_union(ranges))


class Symbol:
    def __init__(self, location: Location):
        self.location = location


class ModsigSymbol(Symbol):
    PATTERN = re.compile(r'modsig')
    def __init__(self, location: Location, name: TokenWithLocation):
        super().__init__(location)
        self.name = name

    @classmethod
    def from_environment(cls, e: Environment) -> Optional[ModsigSymbol]:
        match = ModsigSymbol.PATTERN.fullmatch(e.env_name)
        if not match:
            return
        if len(e.rargs) != 1:
            raise ValueError(f'RArg count mismatch (expected 1, found {len(e.rargs)}).')
        return ModsigSymbol(e.location, TokenWithLocation.from_node(e.rargs[0]))

    def __repr__(self):
        return f'[module name={self.name}]'


class MhmodnlSymbol(Symbol):
    PATTERN = re.compile(r'mhmodnl')
    def __init__(self, location: Location, name: TokenWithLocation, lang: TokenWithLocation):
        super().__init__(location)
        self.name = name
        self.lang = lang

    @classmethod
    def from_environment(cls, e: Environment) -> Optional[MhmodnlSymbol]:
        match = MhmodnlSymbol.PATTERN.fullmatch(e.env_name)
        if not match:
            return
        if len(e.rargs) != 2:
            raise ValueError(f'RArg count mismatch (expected 2, found {len(e.rargs)}).')
        return MhmodnlSymbol(
            e.location,
            TokenWithLocation.from_node(e.rargs[0]),
            TokenWithLocation.from_node(e.rargs[1])
        )

    def __repr__(self):
        return f'[binding name={self.name} lang={self.lang}]'


class DefiSymbol(Symbol):
    PATTERN = re.compile(r'([ma]*)def([ivx]+)(s)?(\*)?')
    def __init__(
        self,
        location: Location,
        tokens: List[TokenWithLocation],
        options: Optional[TokenWithLocation],
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
    def from_environment(cls, e: Environment) -> Optional[DefiSymbol]:
        match = DefiSymbol.PATTERN.fullmatch(e.env_name)
        if match is None:
            return None
        if not e.rargs:
            raise ValueError('RArg count mismatch (expected at least 1, found 0).')
        if len(e.oargs) > 1:
            raise ValueError(f'OArg count mismatch (expected at most 1, found {len(e.oargs)})')
        return DefiSymbol(
            e.location,
            list(map(TokenWithLocation.from_node, e.rargs)),
            TokenWithLocation.from_node_union(e.oargs),
            'm' in match.group(1),
            'a' in match.group(1),
            roman_numerals.roman2int(match.group(2)),
            match.group(3) is not None,
            match.group(4) is not None)

    def __repr__(self):
        return f'[defi options="{self.options}" tokens={self.tokens}]'


class TrefiSymbol(Symbol):
    PATTERN = re.compile(r'([ma]*)tref([ivx]+)(s)?(\*)?')
    def __init__(
        self,
        location: Location,
        tokens: List[TokenWithLocation],
        options: Optional[TokenWithLocation],
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
    def from_environment(cls, e: Environment) -> Optional[TrefiSymbol]:
        match = TrefiSymbol.PATTERN.fullmatch(e.env_name)
        if match is None:
            return None
        if not e.rargs:
            raise ValueError('RArg count mismatch (expected at least 1, found 0).')
        if len(e.oargs) > 1:
            raise ValueError(f'OArg count mismatch (expected at most 1, found {len(e.oargs)})')
        return TrefiSymbol(
            e.location,
            list(map(TokenWithLocation.from_node, e.rargs)),
            TokenWithLocation.from_node_union(e.oargs),
            'm' in match.group(1),
            'a' in match.group(1),
            roman_numerals.roman2int(match.group(2)),
            match.group(3) is not None,
            match.group(4) is not None,
        )

    def __repr__(self):
        return f'[trefi options="{self.options}" tokens={self.tokens}]'


class SymiSymbol(Symbol):
    PATTERN = re.compile(r'sym([ivx]+)(s)?(\*)?')
    def __init__(
        self,
        location: Location,
        tokens: List[TokenWithLocation],
        i: int,
        s: bool,
        asterisk: bool):
        super().__init__(location)
        self.tokens = tokens
        self.i = i
        self.s = s
        self.asterisk = asterisk

    @classmethod
    def from_environment(cls, e: Environment) -> Optional[SymiSymbol]:
        match = SymiSymbol.PATTERN.fullmatch(e.env_name)
        if match is None:
            return None
        if not e.rargs:
            raise ValueError('RArg count mismatch (expected at least 1, found 0).')
        return SymiSymbol(
            e.location,
            list(map(TokenWithLocation.from_node, e.rargs)),
            roman_numerals.roman2int(match.group(1)),
            match.group(2) is not None,
            match.group(3) is not None,
        )

    def __repr__(self):
        return f'[sym{"*"*self.asterisk} i={self.i} s={self.s} tokens={self.tokens}]'


class SymdefSymbol(Symbol):
    PATTERN = re.compile(r'symdef(\*)?')
    def __init__(self, location: Location, tokens: List[TokenWithLocation], options: Optional[TokenWithLocation], asterisk: bool):
        super().__init__(location)
        self.tokens = tokens
        self.options = options
        self.asterisk = asterisk

    @classmethod
    def from_environment(cls, e: Environment) -> Optional[SymdefSymbol]:
        match = SymdefSymbol.PATTERN.fullmatch(e.env_name)
        if match is None:
            return None
        if not e.rargs:
            raise ValueError('RArg count mismatch: At least one RArg required.')
        return SymdefSymbol(
            e.location,
            list(map(TokenWithLocation.from_node, e.rargs)),
            TokenWithLocation.from_node_union(e.oargs) if e.oargs else None,
            match.group(1) is not None,
        )

    def __repr__(self):
        return f'[symdef{"*"*self.asterisk} options="{self.options if self.options else ""}" tokens={self.tokens}]'


class GImportSymbol(Symbol):
    PATTERN = re.compile(r'gimport(\*)?')
    def __init__(self, location: Location, target: TokenWithLocation, options: Optional[TokenWithLocation], asterisk: bool):
        super().__init__(location)
        self.target = target
        self.options = options
        self.asterisk = asterisk

    @classmethod
    def from_environment(cls, e: Environment) -> Optional[GImportSymbol]:
        match = GImportSymbol.PATTERN.fullmatch(e.env_name)
        if match is None:
            return None
        if not e.rargs:
            raise ValueError('RArg count mismatch (expected at least 1, found 0).')
        if len(e.oargs) > 1:
            raise ValueError(f'OArg count mismatch (expected at most 1, found {len(e.oargs)})')
        return GImportSymbol(
            e.location,
            TokenWithLocation.from_node_union(e.rargs),
            TokenWithLocation.from_node_union(e.oargs),
            match.group(1) is not None,
        )

    def __repr__(self):
        return f'[gimport{"*"*self.asterisk} options="{self.options}" target={self.target}]'


class GStructureSymbol(Symbol):
    PATTERN = re.compile(r'gstructure(\*)?')
    def __init__(self, location: Location, asterisk: bool):
        super().__init__(location)
        self.asterisk = asterisk
        raise NotImplementedError

    @classmethod
    def from_environment(cls, e: Environment) -> Optional[GStructureSymbol]:
        match = GStructureSymbol.PATTERN.fullmatch(e.env_name)
        if match is None:
            return None


class GUseSymbol(Symbol):
    def __init__(self, location):
        super().__init__(location)
        raise NotImplementedError

