from __future__ import annotations
from typing import Optional, Tuple, List, Dict, Set
import re
import multiprocessing
from collections import defaultdict
from pathlib import Path
from stexls.util import roman_numerals
from stexls.util.location import Location, Range, Position
from stexls.util.latex.parser import Environment, Node, LatexParser, OArgument
from .exceptions import CompilerException, CompilerWarning
from stexls.util.latex.exceptions import LatexException

__all__ = (
    'ParsedFile',
    'ParsedEnvironment',
    'parse',
    'parse_recursive',
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
        self.errors: Dict[Location, List[Exception]] = defaultdict(list)


def parse_recursive(path: Path) -> Tuple[List[ParsedFile], Dict[Location, List[Exception]]]:
    paths = [path]
    visited = set()
    result: List[ParsedFile] = []
    exceptions: Dict[Location, List[Exception]] = {}
    with multiprocessing.Pool() as pool:
        while paths:
            parsed_files = pool.map(parse, paths)
            for path in paths:
                visited.add(path)
            result.extend(parsed_files)
            paths = []
            for file in parsed_files:
                module_paths = []
                for mhmodnl in file.mhmodnls:
                    module_paths.append((mhmodnl.location, mhmodnl.path_to_module_file, mhmodnl.name))
                for gimport in file.gimports:
                    module_paths.append((gimport.location, gimport.module_path, gimport.target))
                for location, module_path, module_name in module_paths:
                    if module_path in visited or module_path in paths:
                        continue
                    if not module_path.is_file():
                        exceptions.setdefault(location, []).append(Exception(f'Unable to import module "{module_name}": "{module_path}" is not a file.'))
                    else:
                        paths.append(module_path)
    return list(reversed(result)), exceptions

def parse(path: Path) -> ParsedFile:
    parsed_file = ParsedFile(path)
    exceptions: List[Tuple[Location, Exception]] = []
    try:
        parser = LatexParser(path)
        parser.parse()
        exceptions = parser.syntax_errors or []
        parser.walk(lambda env: _visitor(env, parsed_file, exceptions))
    except (CompilerException, LatexException) as ex:
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
        exceptions.append((whole_file_location, ex))
    for loc, e in exceptions:
        parsed_file.errors[loc].append(e)
    return parsed_file

def _visitor(env: Environment, parsed_file: ParsedFile, exceptions: List[Tuple[Location, Exception]]):
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
    except CompilerException as e:
        exceptions.append((env.location, e))
        return


class TokenWithLocation:
    def __init__(self, text: str, range: Range):
        self.text = text
        self.range = range

    def __repr__(self):
        return self.text
    
    @staticmethod
    def parse_oargs(oargs: List[OArgument]) -> Tuple[List[TokenWithLocation], Dict[str, TokenWithLocation]]:
        unnamed = [
            TokenWithLocation.from_node(oarg.value)
            for oarg in oargs
            if oarg.name is None
        ]
        named = {
            oarg.name.text[:-1]: TokenWithLocation.from_node(oarg.value)
            for oarg in oargs
            if oarg.name is not None
        }
        return unnamed, named

    def split(self, index: int, offset: int = 0) -> Optional[Tuple[TokenWithLocation, TokenWithLocation]]:
        ''' Splits the token at the specified index.

        Arguments:
            index: The index on where to split the token.
            offset: Optional character offset of second split.
        
        Examples:
            >>> range = Range(Position(1, 5), Position(1, 18))
            >>> text = 'module?symbol'
            >>> token = TokenWithLocation(text, range)
            >>> left, right = token.split(text.index('?'), offset=1)
            >>> left
            'module'
            >>> left.range
            [Range (1 5) (1 11)]
            >>> right
            'symbol'
            >>> right.range
            [Range (1 12) (1 18)]
            >>> _, right = token.split(text.index('?'), offset=0)
            >>> right
            '?symbol'
            >>> right.range
            [Range (1 11) (1 18)]
        '''
        ltext = self.text[:index]
        rtext = self.text[index + offset:]
        lrange, rrange = self.range.split(index)
        return TokenWithLocation(ltext, lrange), TokenWithLocation(rtext, rrange)

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
        return Modsig(
            e.location,
            TokenWithLocation.from_node(e.name))

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
        return (self.location.uri.parents[0] / (self.name.text + '.tex')).absolute()
    
    @classmethod
    def from_environment(cls, e: Environment) -> Optional[Mhmodnl]:
        match = Mhmodnl.PATTERN.fullmatch(e.env_name)
        if not match:
            return
        if len(e.rargs) != 2:
            raise CompilerException(f'Argument count mismatch (expected 2, found {len(e.rargs)}).')
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
        name_arg: Optional[TokenWithLocation],
        m: bool,
        a: bool,
        capital: bool,
        i: int,
        s: bool,
        asterisk: bool):
        super().__init__(location)
        self.tokens = tokens
        self.name_arg = name_arg
        self.m = m
        self.capital = capital
        self.a = a
        self.i = i
        self.s = s
        self.asterisk = asterisk
        if i != len(tokens) - int(a):
            raise CompilerException(f'Defi argument count mismatch: Expected {i} vs actual {len(tokens) - int(a)}.')

    @property
    def name(self) -> str:
        if self.name_arg:
            return self.name_arg.text
        if self.a:
            return '-'.join(t.text for t in self.tokens[1:])
        return '-'.join(t.text for t in self.tokens)

    @classmethod
    def from_environment(cls, e: Environment) -> Optional[Defi]:
        match = Defi.PATTERN.fullmatch(e.env_name)
        if match is None:
            return None
        if not e.rargs:
            raise CompilerException('Argument count mismatch (expected at least 1, found 0).')
        _, named = TokenWithLocation.parse_oargs(e.oargs)
        return Defi(
            location=e.location,
            tokens=list(map(TokenWithLocation.from_node, e.rargs)),
            name_arg=named.get('name'),
            m='m' in match.group(1),
            a='a' in match.group(1),
            capital=match.group(2) == 'D',
            i=roman_numerals.roman2int(match.group(3)),
            s=match.group(4) is not None,
            asterisk=match.group(5) is not None)

    def __repr__(self):
        return f'[Defi tokens={self.tokens}]'


class Trefi(ParsedEnvironment):
    PATTERN = re.compile(r'([ma]*)(t|T)ref([ivx]+)(s)?(\*)?')
    def __init__(
        self,
        location: Location,
        tokens: List[TokenWithLocation],
        target_annotation: Optional[TokenWithLocation],
        m: bool,
        a: bool,
        capital: bool,
        i: int,
        s: bool,
        asterisk: bool):
        super().__init__(location)
        self.tokens = tokens
        self.target_annotation = target_annotation
        self.m = m
        self.a = a
        self.capital = capital
        self.i = i
        self.s = s
        self.asterisk = asterisk
        actual = len(tokens) - int(a)
        if i != actual:
            raise CompilerException(f'Trefi argument count mismatch: Expected {i} vs. actual {actual}.')
        has_q = self.target_annotation and '?' in self.target_annotation.text
        if not self.m and has_q:
            raise CompilerException('Question mark syntax "?<symbol>" syntax not allowed in non-mtrefi environments.')
        if self.m and not has_q:
            raise CompilerException('Invalid "mtref" environment: Target symbol must be clarified by using "?<symbol>" syntax.')
    
    @property
    def target_symbol(self) -> str:
        ''' Parses the targeted symbol's name.

        The target's name is either given in the annotations
        by using the ?<symbol> syntax or else it is generated
        by joining the tokens with a '-' character.
        '''
        if self.target_annotation and '?' in self.target_annotation.text:
            return self.target_annotation.text.split('?')[-1].strip()
        tokens = (t.text for t in self.tokens[int(self.a):])
        generated = '-'.join(tokens)
        return generated.strip()

    @property
    def target_module(self) -> Optional[TokenWithLocation]:
        ''' Parses the targeted module's name if specified in oargs.
        
        Returns None if no module is explicitly named.
        '''
        if self.target_annotation:
            if '?' in self.target_annotation.text:
                index = self.target_annotation.text.index('?')
                left, _ = self.target_annotation.split(index, 1)
                if left.text:
                    return left # return left in case of <module>?<symbol>
                return None # return None in case of ?symbol
            return self.target_annotation # return the whole thing in case of [module]
        return None # return None if no oargs are given

    @classmethod
    def from_environment(cls, e: Environment) -> Optional[Trefi]:
        match = Trefi.PATTERN.fullmatch(e.env_name)
        if match is None:
            return None
        if not e.rargs:
            raise CompilerException('Argument count mismatch (expected at least 1, found 0).')
        if len(e.unnamed_args) > 1:
            raise CompilerException(f'Too many unnamed oargs in trefi: Expected are at most 1, found {len(options)}')
        annotations = (
            TokenWithLocation.from_node(e.unnamed_args[0])
            if e.unnamed_args
            else None
        )
        tokens = list(map(TokenWithLocation.from_node, e.rargs))
        return Trefi(
            location=e.location,
            tokens=tokens,
            target_annotation=annotations,
            m='m' in match.group(1),
            a='a' in match.group(1),
            capital=match.group(2) == 'T',
            i=roman_numerals.roman2int(match.group(3)),
            s=match.group(4) is not None,
            asterisk=match.group(5) is not None,
        )

    def __repr__(self):
        return f'[Trefi module="{self.target_module}" symbol="{self.target_symbol}"]'


class _NoverbHandler:
    def __init__(
        self,
        unnamed: List[TokenWithLocation],
        named: Dict[str, TokenWithLocation]):
        self.unnamed = unnamed
        self.named = named

    @property
    def is_all(self) -> bool:
        return any(arg.text == 'noverb' for arg in self.unnamed)

    @property
    def langs(self) -> Set[str]:
        noverb: TokenWithLocation = self.named.get('noverb')
        if noverb is None:
            return set()
        if (noverb.text[0], noverb.text[-1]) == ('{', '}'):
            return set(noverb.text[1:-1].split(','))
        return set([noverb.text])


class Symi(ParsedEnvironment):
    PATTERN = re.compile(r'sym([ivx]+)(\*)?')
    def __init__(
        self,
        location: Location,
        tokens: List[TokenWithLocation],
        unnamed_args: List[TokenWithLocation],
        named_args: Dict[str, TokenWithLocation],
        i: int,
        asterisk: bool):
        super().__init__(location)
        self.tokens = tokens
        self.noverb = _NoverbHandler(unnamed_args, named_args)
        self.i = i
        self.asterisk = asterisk
        if i != len(tokens):
            raise CompilerException(f'Symi argument count mismatch: Expected {i} vs actual {len(tokens)}.')
    
    @property
    def name(self) -> str:
        return '-'.join(token.text for token in self.tokens)

    @classmethod
    def from_environment(cls, e: Environment) -> Optional[Symi]:
        match = Symi.PATTERN.fullmatch(e.env_name)
        if match is None:
            return None
        if not e.rargs:
            raise CompilerException('Argument count mismatch (expected at least 1, found 0).')
        unnamed, named = TokenWithLocation.parse_oargs(e.oargs)
        return Symi(
            location=e.location,
            tokens=list(map(TokenWithLocation.from_node, e.rargs)),
            unnamed_args=unnamed,
            named_args=named,
            i=roman_numerals.roman2int(match.group(1)),
            asterisk=match.group(2) is not None,
        )

    def __repr__(self):
        return f'[Sym{"*"*self.asterisk} i={self.i} tokens={self.tokens}]'


class Symdef(ParsedEnvironment):
    PATTERN = re.compile(r'symdef(\*)?')
    def __init__(
        self,
        location: Location,
        tokens: List[TokenWithLocation],
        target_annotation: Optional[TokenWithLocation],
        asterisk: bool):
        super().__init__(location)
        self.tokens = tokens
        self.target_annotation = target_annotation
        self.asterisk = asterisk
    
    @property
    def name(self) -> str:
        if self.target_annotation is None:
            return self.tokens[0].text
        return self.target_annotation.text

    @classmethod
    def from_environment(cls, e: Environment) -> Optional[Symdef]:
        match = Symdef.PATTERN.fullmatch(e.env_name)
        if match is None:
            return None
        if not e.rargs:
            raise CompilerException('Argument count mismatch: At least one argument required.')
        tokens = list(map(TokenWithLocation.from_node, e.rargs))
        _, named = TokenWithLocation.parse_oargs(e.oargs)
        return Symdef(
            location=e.location,
            tokens=tokens,
            target_annotation=named.get('name'),
            asterisk=match.group(1) is not None,
        )

    def __repr__(self):
        return f'[Symdef{"*"*self.asterisk} target="{self.target_annotation or ""}" tokens={self.tokens}]'


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
            >>> actual = gimport.repository_path_annotation.as_posix()
            >>> expected = Path('smglom/example-repo/source').absolute()
            >>> expected == actual
            True
        '''
        if self.options is None:
            return None
        return Path(self.options.text).absolute() / 'source'

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
            raise CompilerException(f'Argument count mismatch (expected 1, found {len(e.rargs)}).')
        if len(e.oargs) > 1:
            raise CompilerException(f'Optional argument count mismatch (expected at most 1, found {len(e.oargs)})')
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

