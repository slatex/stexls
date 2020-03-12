from __future__ import annotations
from typing import Optional, Tuple, List, Dict
import re
from pathlib import Path
from stexls.util import roman_numerals
from stexls.util.location import Location, Range, Position
from stexls.util.latex.parser import Environment, Node, LatexParser

__all__ = (
    'ParsedFile',
    'ParsedEnvironment',
    'parse',
    'TokenWithLocation',
    'Location',
    'Modsig',
    'Mhmodnl',
    'Trefi',
    'Defi',
    'Symi',
    'Symdef',
    'GImport',
    'GStructure',
    'GUse',
)

class ParsedFile:
    " An object contains information about symbols, locations, imports of an stex source file. "
    def __init__(self, path: Path):
        self.path = path
        self.modsigs: List[Modsig] = []
        self.mhmodnls: List[Mhmodnl] = []
        self.trefis: List[Trefi] = []
        self.defis: List[Defi] = []
        self.syms: List[Symi] = []
        self.symdefs: List[Symdef] = []
        self.gimports: List[GImport] = []


def parse(path: Path, debug_exceptions: bool = False) -> ParsedFile:
    parsed_file = ParsedFile(path)
    exceptions: List[Tuple[Location, Exception]] = []
    try:
        parser = LatexParser(path)
        parser.parse()
        exceptions = parser.syntax_errors or []
        parser.walk(lambda env: _visitor(env, parsed_file, exceptions))
    except Exception as e1:
        if debug_exceptions:
            raise
        try:
            with open(path, mode='r') as f:
                lines = f.readlines()
        except:
            lines = []
        last_line = len(lines)
        last_character = len(lines[-1]) if lines else 0
        end_position = Position(last_line, last_character)
        whole_file_range = Range(Position(0, 0), end_position)
        whole_file_location = Location(path, whole_file_range)
        exceptions.append((whole_file_location, e1))
    parsed_file.exceptions = exceptions
    return parsed_file

def _visitor(env: Environment, parsed_file: ParsedFile, exceptions: List[Tuple[Location, Exception]], debug_exceptions: bool = True):
    try:
        module = Modsig.from_environment(env)
        if module:
            parsed_file.modsigs.append(module)
            return
        binding = Mhmodnl.from_environment(env)
        if binding:
            parsed_file.mhmodnls.append(binding)
            return
        trefi = Trefi.from_environment(env)
        if trefi:
            parsed_file.trefis.append(trefi)
            return
        defi = Defi.from_environment(env)
        if defi:
            parsed_file.defis.append(defi)
            return
        sym = Symi.from_environment(env)
        if sym:
            parsed_file.syms.append(sym)
            return
        symdef = Symdef.from_environment(env)
        if symdef:
            parsed_file.symdefs.append(symdef)
            return
        gimport = GImport.from_environment(env)
        if gimport:
            parsed_file.gimports.append(gimport)
            return
    except Exception as e:
        if debug_exceptions:
            raise
        exceptions.append((env.location, e))
        return


class TokenWithLocation:
    def __init__(self, text: str, range: Range):
        self.text = text
        self.range = range
    
    def parse_options(self) -> Tuple[Tuple[List[str], Dict[str, str]], Tuple[List[Range], Dict[str, Range]]]:
        """ Parses the text attribute as a comma seperated
        list of options which are either named and prefixed
        with "<name>=" or unnamed.

        TODO: This fails when summarizing optional arguments.
        E.g.: \symdef[noverb]{NumberPrimeNumber}[1]{...}
        In this case, "noverb" and "1" will be summarized to "noverb,1" and the position of the "1" token will be wrong.

        Returns:
            The string is parsed as a tuple of a list of the
            unnamed options "[unnamed,unnamed2]", in this case.
            And as a dictionary of named options:
            {"named1":"value1","named2":"value2"}
            Additionally returns a tuple of a list of ranges for the
            unnamed values and a dict from name to named value ranges.

        Examples:
            >>> token = TokenWithLocation('name=value,1', Range(Position(1, 1), Position(1, 13)))
            >>> values, ranges = token.parse_options()
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
        for line in self.text.split('\n'):
            for part in line.split(','):
                if '=' in part:
                    name, value = part.split('=', 1)
                    named[name.strip()] = value.strip()
                    new_start = self.range.start.translate(
                        characters=offset + len(name) + 1) # +1 for '=' char
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
                offset += len(part) + 1 # +1 for ',' character
            offset += 1 # +1 for line end
        return (unnamed, named), (unnamed_ranges, named_ranges)


    def __repr__(self):
        return self.text

    @staticmethod
    def from_node(node: Node) -> TokenWithLocation:
        return TokenWithLocation(node.text_inside, node.location.range)

    @staticmethod
    def from_node_union(nodes: List[Node], separator: str = ',') -> Optional[TokenWithLocation]:
        tags = map(TokenWithLocation.from_node, nodes)
        values, ranges = zip(*((tok.text, tok.range) for tok in tags))
        return TokenWithLocation(separator.join(values), Range.big_union(ranges))


class ParsedEnvironment:
    def __init__(self, location: Location):
        self.location = location


class Modsig(ParsedEnvironment):
    PATTERN = re.compile(r'modsig')
    def __init__(self, location: Location, name: TokenWithLocation):
        super().__init__(location)
        self.name = name
    
    @classmethod
    def from_environment(cls, e: Environment) -> Optional[Modsig]:
        match = Modsig.PATTERN.fullmatch(e.env_name)
        if not match:
            return
        if len(e.rargs) != 1:
            raise ValueError(f'Argument count mismatch (expected 1, found {len(e.rargs)}).')
        return Modsig(e.location, TokenWithLocation.from_node(e.rargs[0]))

    def __repr__(self):
        return f'[Modsig name={self.name.text}]'


class Mhmodnl(ParsedEnvironment):
    PATTERN = re.compile(r'mhmodnl')
    def __init__(self, location: Location, name: TokenWithLocation, lang: TokenWithLocation):
        super().__init__(location)
        self.name = name
        self.lang = lang

    @property
    def path_to_module_file(self) -> Path:
        ''' Guesses the path to the file of the attached module.

        Takes the path of the file this language binding is located and
        returns the default path to the attached module.

        Returns:
            Path: Path to module file.
        
        Examples:
            >>> binding_path = Path('path/to/glossary/repo/source/module/module.lang.tex')
            >>> binding_location = Location(binding_path, None)
            >>> module_name = TokenWithLocation('module', None)
            >>> binding_lang = TokenWithLocation('lang', None)
            >>> binding = Mhmodnl(binding_location, module_name, binding_lang)
            >>> binding.path_to_module_file.as_posix()
            'path/to/glossary/repo/source/module/module.tex'
        '''
        return self.location.uri.parents[0] / (self.name.text + '.tex')
    
    @classmethod
    def from_environment(cls, e: Environment) -> Optional[Mhmodnl]:
        match = Mhmodnl.PATTERN.fullmatch(e.env_name)
        if not match:
            return
        if len(e.rargs) != 2:
            raise ValueError(f'Argument count mismatch (expected 2, found {len(e.rargs)}).')
        return Mhmodnl(
            e.location,
            TokenWithLocation.from_node(e.rargs[0]),
            TokenWithLocation.from_node(e.rargs[1])
        )

    def __repr__(self):
        return f'[Binding name={self.name.text} lang={self.lang.text}]'


class Defi(ParsedEnvironment):
    PATTERN = re.compile(r'([ma]*)(d|D)ef([ivx]+)(s)?(\*)?')
    def __init__(
        self,
        location: Location,
        tokens: List[TokenWithLocation],
        options: Optional[TokenWithLocation],
        m: bool,
        capital: bool,
        a: bool,
        i: int,
        s: bool,
        asterisk: bool):
        super().__init__(location)
        self.tokens = tokens
        self.options = options
        self.m = m
        self.capital = capital
        self.a = a
        self.i = i
        self.s = s
        self.asterisk = asterisk
        if i != len(tokens) - int(a):
            raise ValueError(f'Defi argument count mismatch: Expected {i} vs actual {len(tokens) - int(a)}.')

    @property
    def name(self) -> str:
        '''
        Examples:
            >>> defi_explicit = Defi(None, None, TokenWithLocation('name=defi-name', None), False, False, False, 0, False, False)
            >>> defi_explicit.name
            'defi-name'
            >>> defi_generated = Defi(None, [TokenWithLocation('defi', None), TokenWithLocation('name', None), TokenWithLocation('generated', None)], None, False, False, False, 0, False, False)
            >>> defi_generated.name
            'defi-name-generated'
            >>> adefi_generated = Defi(None, [TokenWithLocation('defi', None), TokenWithLocation('name', None), TokenWithLocation('generated', None)], None, False, False, True, 0, False, False)
            >>> adefi_generated.name
            'name-generated'
        '''
        if self.options:
            values, ranges = self.options.parse_options()
            name = values[-1].get('name')
            if name:
                return name
        if self.a:
            return '-'.join(t.text for t in self.tokens[1:])
        return '-'.join(t.text for t in self.tokens)

    @classmethod
    def from_environment(cls, e: Environment) -> Optional[Defi]:
        match = Defi.PATTERN.fullmatch(e.env_name)
        if match is None:
            return None
        if not e.rargs:
            raise ValueError('Argument count mismatch (expected at least 1, found 0).')
        if len(e.oargs) > 1:
            raise ValueError(f'Optional argument count mismatch (expected at most 1, found {len(e.oargs)})')
        return Defi(
            e.location,
            list(map(TokenWithLocation.from_node, e.rargs)),
            TokenWithLocation.from_node_union(e.oargs) if e.oargs else None,
            'm' in match.group(1),
            'a' in match.group(1),
            match.group(2) == 'D',
            roman_numerals.roman2int(match.group(3)),
            match.group(4) is not None,
            match.group(5) is not None)

    def __repr__(self):
        return f'[Defi options="{self.options if self.options else ""}" tokens={self.tokens}]'


class Trefi(ParsedEnvironment):
    PATTERN = re.compile(r'([ma]*)(t|T)ref([ivx]+)(s)?(\*)?')
    def __init__(
        self,
        location: Location,
        tokens: List[TokenWithLocation],
        options: Optional[TokenWithLocation],
        m: bool,
        a: bool,
        capital: bool,
        i: int,
        s: bool,
        asterisk: bool):
        super().__init__(location)
        self.tokens = tokens
        self.options = options
        self.m = m
        self.a = a
        self.capital = capital
        self.i = i
        self.s = s
        self.asterisk = asterisk
        actual = len(tokens) - int(a)
        if i != actual:
            raise ValueError(f'Trefi argument count mismatch: Expected {i} vs. actual {actual}.')
        if self.options and (not self.m and '?' in self.options.text):
            raise ValueError('Questionmark syntax "?<symbol>" syntax not allowed in non-mtrefi environments.')
        if self.m and not self.options:
            raise ValueError('Invalid "mtref" environment: Target symbol must be clarified by using "?<symbol>" syntax.')
    
    @property
    def target_symbol(self) -> str:
        ''' Parses the targeted symbol's name.

        The target's name is either given in the annotations
        by using the ?<symbol> syntax or else it is generated
        by joining the tokens with a '-' character.
        '''
        _, target_symbol, _, _ = self.parse_annotations()
        if target_symbol is not None:
            return target_symbol
        tokens = (t.text for t in self.tokens[int(self.a):])
        generated = '-'.join(tokens)
        return generated

    def parse_annotations(self) -> Tuple[Optional[str], Optional[str], Optional[Range], Optional[Range]]:
        ''' Parses module and symbol annotations from optional arguments.

        Returns:
            A tuple of (module, symbol, module_range, symbol_range).
            module: Name of the module named in the annotation (trefi[<module>?...] or trefi[<module>]...)
            symbol: Name of the symbol named in the annotation (trefi[...?<symbol>]...)
            module_range: The range of the part which names the target module if it exists.
            symbol_range: The range of the part which names the target symbol if it exists.
        
        Examples:
            >>> range = Range(Position(2, 5), Position(2, 33))
            >>> token = TokenWithLocation('vector-space?vector-addition', range)
            >>> trefi = Trefi(None, [], token, False, False, False, 0, False, False)
            >>> module, symbol, mrange, srange = trefi.parse_annotations()
            >>> module
            'vector-space'
            >>> symbol
            'vector-addition'
            >>> mrange
            [Range (2 5) (2 17)]
            >>> srange
            [Range (2 18) (2 33)]
            >>> range = Range(Position(2, 5), Position(2, 18))
            >>> token = TokenWithLocation('vector-space2', range)
            >>> trefi = Trefi(None, [], token, False, False, False, 0, False, False)
            >>> module, symbol, mrange, srange = trefi.parse_annotations()
            >>> module
            'vector-space2'
            >>> symbol is None
            True
            >>> mrange
            [Range (2 5) (2 18)]
            >>> srange is None
            True
        '''
        (unnamed, named), (unnamed_range, named_ranges) = self.options.parse_options()
        if len(unnamed) != 1 or len(unnamed_range) != 1:
            return None, None, None, None
        annotation: str = unnamed[0]
        annotation_range: Range = unnamed_range[0]
        if '?' in annotation:
            module_annotation, symbol_annotation = annotation.split('?')
            module_range, symbol_range = annotation_range.split(annotation.index('?'))
            symbol_range.start.character += 1
            return module_annotation, symbol_annotation, module_range, symbol_range
        return annotation, None, annotation_range, None

    @classmethod
    def from_environment(cls, e: Environment) -> Optional[Trefi]:
        match = Trefi.PATTERN.fullmatch(e.env_name)
        if match is None:
            return None
        if not e.rargs:
            raise ValueError('Argument count mismatch (expected at least 1, found 0).')
        if len(e.oargs) > 1:
            raise ValueError(f'Optional argument count mismatch (expected at most 1, found {len(e.oargs)})')
        return Trefi(
            e.location,
            list(map(TokenWithLocation.from_node, e.rargs)),
            TokenWithLocation.from_node_union(e.oargs),
            'm' in match.group(1),
            'a' in match.group(1),
            match.group(2) == 'T',
            roman_numerals.roman2int(match.group(3)),
            match.group(4) is not None,
            match.group(5) is not None,
        )

    def __repr__(self):
        return f'[Trefi options="{self.options if self.options else ""}" tokens={self.tokens}]'


class Symi(ParsedEnvironment):
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
        if i != len(tokens):
            raise ValueError(f'Symi argument count mismatch: Expected {i} vs actual {len(tokens)}.')
    
    @property
    def name(self) -> str:
        return '-'.join(token.text for token in self.tokens)

    @classmethod
    def from_environment(cls, e: Environment) -> Optional[Symi]:
        match = Symi.PATTERN.fullmatch(e.env_name)
        if match is None:
            return None
        if not e.rargs:
            raise ValueError('Argument count mismatch (expected at least 1, found 0).')
        return Symi(
            e.location,
            list(map(TokenWithLocation.from_node, e.rargs)),
            roman_numerals.roman2int(match.group(1)),
            match.group(2) is not None,
            match.group(3) is not None,
        )

    def __repr__(self):
        return f'[Sym{"*"*self.asterisk} i={self.i} s={self.s} tokens={self.tokens}]'


class Symdef(ParsedEnvironment):
    PATTERN = re.compile(r'symdef(\*)?')
    def __init__(self, location: Location, tokens: List[TokenWithLocation], options: Optional[TokenWithLocation], asterisk: bool):
        super().__init__(location)
        self.tokens = tokens
        self.options = options
        self.asterisk = asterisk
    
    @property
    def name(self) -> str:
        if self.options is None:
            return self.tokens[0].text
        values, ranges = self.options.parse_options()
        name = values[-1].get('name')
        if name is not None:
            return name
        return self.tokens[0].text

    @classmethod
    def from_environment(cls, e: Environment) -> Optional[Symdef]:
        match = Symdef.PATTERN.fullmatch(e.env_name)
        if match is None:
            return None
        if not e.rargs:
            raise ValueError('Argument count mismatch: At least one argument required.')
        return Symdef(
            e.location,
            list(map(TokenWithLocation.from_node, e.rargs)),
            TokenWithLocation.from_node_union(e.oargs) if e.oargs else None,
            match.group(1) is not None,
        )

    def __repr__(self):
        return f'[Symdef{"*"*self.asterisk} options="{self.options if self.options else ""}" tokens={self.tokens}]'


class GImport(ParsedEnvironment):
    PATTERN = re.compile(r'gimport(\*)?')
    def __init__(
        self,
        location: Location,
        target: TokenWithLocation,
        options: Optional[TokenWithLocation],
        asterisk: bool):
        super().__init__(location)
        self.target = target
        self.options = options
        self.asterisk = asterisk
    
    @property
    def repository_path_annotation(self) -> Optional[Path]:
        ''' Returns the path to the repository's source dir the oargs annotation points to.

        Examples:
            >>> options = TokenWithLocation('smglom/example-repo', None)
            >>> gimport = GImport(None, None, options, False)
            >>> gimport.repository_path_annotation.as_posix()
            'smglom/example-repo/source'
        '''
        if self.options is None:
            return None
        return Path(self.options.text) / 'source'

    @property
    def module_path(self) -> Path:
        ''' Returns the path to the module file this gimport points to.

        Examples:
            >>> path = Path('path/to/smglom/repo/source/module.tex')
            >>> location = Location(path, None)
            >>> target = TokenWithLocation('target-module')
            >>> gimport = GImport(location, target, None, False)
            >>> gimport.module_path.as_posix() # target module in same repo
            'path/to/smglom/repo/source/target-module.tex
            >>> options = TokenWithLocation('smglom/other-repo', None)
            >>> gimport = GImport(location, target, options, False)
            >>> gimport.module_path.as_posix() # target module in other repo
            'smglom/other-repo/source/target-module.tex'
        '''
        annotation = self.repository_path_annotation
        if annotation:
            return annotation / (self.target_module_name + '.tex')
        return self.location.uri.parents[0] / (self.target_module_name + '.tex')

    @property
    def target_module_name(self) -> str:
        return self.target.text

    @classmethod
    def from_environment(cls, e: Environment) -> Optional[GImport]:
        match = GImport.PATTERN.fullmatch(e.env_name)
        if match is None:
            return None
        if len(e.rargs) != 1:
            raise ValueError(f'Argument count mismatch (expected 1, found {len(e.rargs)}).')
        if len(e.oargs) > 1:
            raise ValueError(f'Optional argument count mismatch (expected at most 1, found {len(e.oargs)})')
        return GImport(
            e.location,
            TokenWithLocation.from_node_union(e.rargs),
            TokenWithLocation.from_node_union(e.oargs) if e.oargs else None,
            match.group(1) is not None,
        )

    def __repr__(self):
        return f'[Gimport{"*"*self.asterisk} options="{self.options or ""}" target={self.target}]'


class GStructure(ParsedEnvironment):
    PATTERN = re.compile(r'gstructure(\*)?')
    def __init__(self, location: Location, asterisk: bool):
        super().__init__(location)
        self.asterisk = asterisk

    @classmethod
    def from_environment(cls, e: Environment) -> Optional[GStructure]:
        match = GStructure.PATTERN.fullmatch(e.env_name)
        if match is None:
            return None
        raise NotImplementedError


class GUse(ParsedEnvironment):
    def __init__(self, location):
        super().__init__(location)
    
    @staticmethod
    def from_environment(e: Environment) -> Optional[GUse]:
        raise NotImplementedError

