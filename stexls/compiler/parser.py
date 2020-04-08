from __future__ import annotations
from typing import Optional, Tuple, List, Dict, Set, Iterator, Union
from collections import defaultdict
from pathlib import Path
import re
import itertools
import multiprocessing

from stexls.util import roman_numerals
from stexls.util.location import Location, Range, Position
from stexls.util.latex.parser import Environment, Node, LatexParser, OArgument
from stexls.util.latex.exceptions import LatexException

from .exceptions import *
from .symbols import *

__all__ = (
    'ParsedFile',
    'ParsedEnvironment',
    'TokenWithLocation',
    'Location',
    'Modsig',
    'Modnl',
    'Module',
    'Trefi',
    'Defi',
    'Symi',
    'Symdef',
    'ImportModule',
    'GImport',
)

class ParsedFile:
    " An object contains information about symbols, locations, imports of an stex source file. "
    def __init__(self, path: Path):
        ' Creates an empty container without actually parsing the file. '
        self.path = Path(path)
        self.modsigs: List[Modsig] = []
        self.modnls: List[Modnl] = []
        self.modules: List[Module] = []
        self.trefis: List[Trefi] = []
        self.defis: List[Defi] = []
        self.syms: List[Symi] = []
        self.symdefs: List[Symdef] = []
        self.importmodules: List[ImportModule] = []
        self.gimports: List[GImport] = []
        self.errors: Dict[Location, List[Exception]] = defaultdict(list)
        self.parsed = False

    def parse(self) -> ParsedFile:
        ' Parse the file from the in the constructor given path. '
        if self.parsed:
            raise ValueError('File already parsed.')
        self.parsed = True
        exceptions: List[Tuple[Location, Exception]] = []
        try:
            parser = LatexParser(self.path)
            parser.parse()
            exceptions = parser.syntax_errors or []
            parser.walk(lambda env: _visitor(env, self, exceptions))
        except (CompilerError, LatexException) as ex:
            exceptions.append((self.default_location, ex))
        for loc, e in exceptions:
            self.errors[loc].append(e)
        return self

    @property
    def toplevels(self) -> Iterator[ParsedFile]:
        """ Splits this file into it's toplevel modules and bindings.
        
        Returns:
            Generator of parsed files which at most contain a single toplevel (module, modsig, modnl)
            and the environments contained in that toplevel environment.
            If no toplevel environment can be found, this file
            is returned instead.
        """
        toplevels = list(itertools.chain(self.modnls, self.modsigs, self.modules))
        if not toplevels:
            yield self
        else:
            for toplevel in toplevels:
                range = toplevel.location.range
                module_file = ParsedFile(self.path)
                module_file.parsed = True
                if isinstance(toplevel, Modsig):
                    module_file.modsigs.append(toplevel)
                elif isinstance(toplevel, Module):
                    module_file.modules.append(toplevel)
                elif isinstance(toplevel, Modnl):
                    module_file.modnls.append(toplevel)
                module_file.trefis = [item for item in self.trefis if range.contains(item.location.range)]
                module_file.defis = [item for item in self.defis if range.contains(item.location.range)]
                module_file.syms = [item for item in self.syms if range.contains(item.location.range)]
                module_file.symdefs = [item for item in self.symdefs if range.contains(item.location.range)]
                module_file.importmodules = [item for item in self.importmodules if range.contains(item.location.range)]
                module_file.gimports = [item for item in self.gimports if range.contains(item.location.range)]
                for loc, item in self.errors.items():
                    if range.contains(loc.range):
                        module_file.errors[loc].extend(item)
                yield module_file

    @property
    def default_location(self) -> Location:
        """ Returns a location with a range that contains the whole file
            or just the range from 0 to 0 if the file can't be openened.
        """
        try:
            with open(self.path) as fd:
                content = fd.read()
            lines = content.split('\n')
            num_lines = len(lines)
            len_last_line = len(lines[-1])
            return Location(self.path, Range(Position(0, 0), Position(num_lines - 1, len_last_line - 1)))
        except:
            return Location(self.path, Position(0, 0))

def _visitor(env: Environment, parsed_file: ParsedFile, exceptions: List[Tuple[Location, Exception]]):
    try:
        module = Modsig.from_environment(env)
        if module:
            parsed_file.modsigs.append(module)
            return
        binding = Modnl.from_environment(env)
        if binding:
            parsed_file.modnls.append(binding)
            return
        module = Module.from_environment(env)
        if module:
            parsed_file.modules.append(module)
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
        importmodule = ImportModule.from_environment(env)
        if importmodule:
            parsed_file.importmodules.append(importmodule)
            return
        gimport = GImport.from_environment(env)
        if gimport:
            parsed_file.gimports.append(gimport)
            return
    except CompilerError as e:
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
    PATTERN = re.compile(r'\\?modsig')
    def __init__(self, location: Location, name: TokenWithLocation):
        super().__init__(location)
        self.name = name
    
    @classmethod
    def from_environment(cls, e: Environment) -> Optional[Modsig]:
        match = Modsig.PATTERN.fullmatch(e.env_name)
        if not match:
            return
        if not e.rargs:
            raise CompilerError('Modsig environment missing required argument: {<module name>}')
        return Modsig(
            e.location,
            TokenWithLocation.from_node(e.rargs[0]))

    def __repr__(self):
        return f'[Modsig name={self.name.text}]'


class Modnl(ParsedEnvironment):
    PATTERN = re.compile(r'\\?(mh)?modnl')
    def __init__(
        self,
        location: Location,
        name: TokenWithLocation,
        lang: TokenWithLocation,
        mh_mode: bool):
        super().__init__(location)
        self.name = name
        self.lang = lang
        self.mh_mode = mh_mode

    @property
    def path(self) -> Path:
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
            >>> binding = Modnl(binding_location, module_name, binding_lang, False)
            >>> binding.path.as_posix()
            'path/to/glossary/repo/source/module/module.tex'
        '''
        return (self.location.uri.parents[0] / (self.name.text + '.tex'))
    
    @classmethod
    def from_environment(cls, e: Environment) -> Optional[Modnl]:
        match = Modnl.PATTERN.fullmatch(e.env_name)
        if not match:
            return
        if len(e.rargs) != 2:
            raise CompilerError(f'Argument count mismatch (expected 2, found {len(e.rargs)}).')
        return Modnl(
            e.location,
            TokenWithLocation.from_node(e.rargs[0]),
            TokenWithLocation.from_node(e.rargs[1]),
            mh_mode=match.group(1) == 'mh',
        )

    def __repr__(self):
        mh = 'mh' if self.mh_mode else ''
        return f'[{mh}Modnl {self.name.text} lang={self.lang.text}]'


class Module(ParsedEnvironment):
    PATTERN = re.compile(r'\\?module(\*)?')
    def __init__(
        self,
        location: Location,
        id: Optional[TokenWithLocation]):
        super().__init__(location)
        self.id = id

    def __repr__(self):
        module = f'id="{self.id.text}"' if self.id else '<anonymous>'
        return f'[Module {module}]'

    @classmethod
    def from_environment(cls, e: Environment) -> Optional[Module]:
        match = cls.PATTERN.match(e.env_name)
        if match is None:
            return None
        _, named = TokenWithLocation.parse_oargs(e.oargs)
        return Module(
            location=e.location,
            id=named.get('id'),
        )


class Defi(ParsedEnvironment):
    PATTERN = re.compile(r'\\?([ma]*)(d|D)ef([ivx]+)(s)?(\*)?')
    def __init__(
        self,
        location: Location,
        tokens: List[TokenWithLocation],
        name_annotation: Optional[TokenWithLocation],
        m: bool,
        a: bool,
        capital: bool,
        i: int,
        s: bool,
        asterisk: bool):
        super().__init__(location)
        self.tokens = tokens
        self.name_annotation = name_annotation
        self.m = m
        self.capital = capital
        self.a = a
        self.i = i
        self.s = s
        self.asterisk = asterisk
        if i + int(a) != len(tokens):
            raise CompilerError(f'Defi argument count mismatch: Expected {i + int(a)} vs actual {len(tokens)}.')

    @property
    def name(self) -> str:
        if self.name_annotation:
            return self.name_annotation.text
        if self.a:
            return '-'.join(t.text for t in self.tokens[1:])
        return '-'.join(t.text for t in self.tokens)

    @classmethod
    def from_environment(cls, e: Environment) -> Optional[Defi]:
        match = Defi.PATTERN.fullmatch(e.env_name)
        if match is None:
            return None
        if not e.rargs:
            raise CompilerError('Argument count mismatch (expected at least 1, found 0).')
        _, named = TokenWithLocation.parse_oargs(e.oargs)
        return Defi(
            location=e.location,
            tokens=list(map(TokenWithLocation.from_node, e.rargs)),
            name_annotation=named.get('name'),
            m='m' in match.group(1),
            a='a' in match.group(1),
            capital=match.group(2) == 'D',
            i=roman_numerals.roman2int(match.group(3)),
            s=match.group(4) is not None,
            asterisk=match.group(5) is not None)

    def __repr__(self):
        return f'[Defi "{self.name}"]'


class Trefi(ParsedEnvironment):
    PATTERN = re.compile(r'\\?([ma]*)(t|T)ref([ivx]+)(s)?(\*)?')
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
        if i + int(a) != len(tokens):
            raise CompilerError(f'Trefi argument count mismatch: Expected {i + int(a)} vs. actual {len(tokens)}.')
        has_q = self.target_annotation and '?' in self.target_annotation.text
        if not self.m and has_q:
            raise CompilerError('Question mark syntax "?<symbol>" syntax not allowed in non-mtrefi environments.')
        if self.m and not has_q:
            raise CompilerError('Invalid "mtref" environment: Target symbol must be clarified by using "?<symbol>" syntax.')
    
    @property
    def name(self) -> str:
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
    def module(self) -> Optional[TokenWithLocation]:
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
            raise CompilerError('Argument count mismatch (expected at least 1, found 0).')
        if len(e.unnamed_args) > 1:
            raise CompilerError(f'Too many unnamed oargs in trefi: Expected are at most 1, found {len(e.unnamed_args)}')
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
        module = f' "{self.module}" ' if self.module else " "
        return f'[Trefi{module}"{self.name}"]'


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
    PATTERN = re.compile(r'\\?sym([ivx]+)(\*)?')
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
            raise CompilerError(f'Symi argument count mismatch: Expected {i} vs actual {len(tokens)}.')
    
    @property
    def name(self) -> str:
        return '-'.join(token.text for token in self.tokens)

    @classmethod
    def from_environment(cls, e: Environment) -> Optional[Symi]:
        match = Symi.PATTERN.fullmatch(e.env_name)
        if match is None:
            return None
        if not e.rargs:
            raise CompilerError('Argument count mismatch (expected at least 1, found 0).')
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
        return f'[Sym{"*"*self.asterisk} "{self.name}"]'


class Symdef(ParsedEnvironment):
    PATTERN = re.compile(r'\\?symdef(\*)?')
    def __init__(
        self,
        location: Location,
        name: TokenWithLocation,
        unnamed_oargs: List[TokenWithLocation],
        named_oargs: Dict[str, TokenWithLocation],
        asterisk: bool):
        super().__init__(location)
        self.name: TokenWithLocation = name
        self.noverb = _NoverbHandler(unnamed_oargs, named_oargs)
        self.asterisk: bool = asterisk

    @classmethod
    def from_environment(cls, e: Environment) -> Optional[Symdef]:
        match = Symdef.PATTERN.fullmatch(e.env_name)
        if match is None:
            return None
        if not e.rargs:
            raise CompilerError('Argument count mismatch: At least one argument required.')
        name = TokenWithLocation.from_node(e.rargs[0])
        unnamed, named = TokenWithLocation.parse_oargs(e.oargs)
        return Symdef(
            location=e.location,
            name=named.get('name', name),
            unnamed_oargs=unnamed,
            named_oargs=named,
            asterisk=match.group(1) is not None,
        )

    def __repr__(self):
        return f'[Symdef{"*"*self.asterisk} "{self.name.text}"]'


class ImportModule(ParsedEnvironment):
    PATTERN = re.compile(r'\\?(import|use)(mh)?module(\*)?')
    def __init__(
        self,
        location: Location,
        module: TokenWithLocation,
        mhrepos: Optional[TokenWithLocation],
        dir: Optional[TokenWithLocation],
        load: Optional[TokenWithLocation],
        path: Optional[TokenWithLocation],
        export: bool,
        mh_mode: bool,
        asterisk: bool):
        super().__init__(location)
        self.module = module
        self.mhrepos = mhrepos
        self.dir = dir
        self.load = load
        self.path = path
        self.export = export
        self.mh_mode = mh_mode
        self.asterisk = asterisk
        if len(list(self.location.uri.parents)) < 4:
            raise CompilerWarning(f'Unable to compile module with a path depth of less than 4: {self.location.uri}')
        if mh_mode:
            # mhimport{}
            # mhimport[dir=..]{}
            # mhimport[path=..]{}
            # mhimport[mhrepos=..,dir=..]{}
            # mhimport[mhrepos=..,path=..]{}
            if dir and path:
                raise CompilerError('Invalid argument configuration in importmhmodule: "dir" and "path" must not be specified at the same time.')
            if mhrepos and not (dir or path):
                raise CompilerError('Invalid argument configuration in importmhmodule: "mhrepos" requires a "dir" or "path" argument.')
            elif load:
                raise CompilerError('Invalid argument configuration in importmhmodule: "load" argument must not be specified.')
        elif mhrepos or dir or path:
            raise CompilerError('Invalid argument configuration in importmodule: "mhrepos", "dir" or "path" must not be specified.')
        elif not load:
            # import[load=..]{}
            raise CompilerError('Invalid argument configuration in importmodule: Missing "load" argument.')
    
    @staticmethod
    def build_path_to_imported_module(
        root: Path,
        current_file: Path,
        mhrepo: Optional[str],
        path: Optional[str],
        dir: Optional[str],
        load: Optional[str],
        filename: str):
        if load:
            return root / load / filename
        if not mhrepo and not path and not dir:
            return current_file
        if mhrepo:
            source: Path = root / mhrepo / 'source'
        else:
            source: Path = root / list(current_file.relative_to(root).parents)[-4]
        assert source.name == 'source', "invalid source directory"
        if dir:
            return source / dir / filename
        elif path:
            return source / (path + '.tex')
        else:
            raise ValueError('Invalid arguments: "path" or "dir" must be specified if "mhrepo" is.')

    def path_to_imported_file(self, root: Path = None) -> Path:
        root = Path.cwd() if root is None else Path(root)
        return ImportModule.build_path_to_imported_module(
            root or Path.cwd(),
            self.location.uri,
            self.mhrepos.text if self.mhrepos else None,
            self.path.text if self.path else None,
            self.dir.text if self.dir else None,
            self.load.text if self.load else None,
            self.module.text + '.tex')

    def __repr__(self):
        access = AccessModifier.PUBLIC if self.export else AccessModifier.PRIVATE
        return f'[{access.value} ImportModule "{self.module.text}" from "{self.path_to_imported_file()}"]'

    @classmethod
    def from_environment(cls, e: Environment) -> Optional[ImportModule]:
        match = ImportModule.PATTERN.fullmatch(e.env_name)
        if match is None:
            return None
        if len(e.rargs) != 1:
            raise CompilerError(f'Argument count mismatch: Expected exactly 1 argument but found {len(e.rargs)}')
        module = TokenWithLocation.from_node(e.rargs[0])
        _, named = TokenWithLocation.parse_oargs(e.oargs)
        return ImportModule(
            location=e.location,
            module=module,
            mhrepos=named.get('mhrepos'),
            dir=named.get('dir'),
            path=named.get('path'),
            load=named.get('load'),
            export=match.group(1) == 'import',
            mh_mode=match.group(2) == 'mh',
            asterisk=match.group(3) == '*'
        )


class GImport(ParsedEnvironment):
    PATTERN = re.compile(r'\\?g(import|use)(\*)?')
    def __init__(
        self,
        location: Location,
        module: TokenWithLocation,
        repository: Optional[TokenWithLocation],
        export: bool,
        asterisk: bool):
        super().__init__(location)
        self.module = module
        self.repository = repository
        self.export = export
        self.asterisk = asterisk

    def path_to_imported_file(self, root: Path = None) -> Path:
        ''' Returns the path to the module file this gimport points to. '''
        root = Path.cwd() if root is None else Path(root)
        filename = self.module.text.strip() + '.tex'
        if self.repository is None:
            return self.location.uri.parents[0] / filename
        source = root / self.repository.text.strip() / 'source'
        return source / filename

    @classmethod
    def from_environment(cls, e: Environment) -> Optional[GImport]:
        match = GImport.PATTERN.fullmatch(e.env_name)
        if match is None:
            return None
        if len(e.rargs) != 1:
            raise CompilerError(f'Argument count mismatch (expected 1, found {len(e.rargs)}).')
        module = TokenWithLocation.from_node(e.rargs[0])
        unnamed, _ = TokenWithLocation.parse_oargs(e.oargs)
        if len(unnamed) > 1:
            raise CompilerError(f'Optional argument count mismatch (expected at most 1, found {len(e.oargs)})')
        return GImport(
            location=e.location,
            module=module,
            repository=next(iter(unnamed), None),
            export=match.group(1) == 'import',
            asterisk=match.group(2) is not None,
        )

    def __repr__(self):
        access = AccessModifier.PUBLIC if self.export else AccessModifier.PRIVATE
        return f'[{access.value} gimport{"*"*self.asterisk} "{self.module.text}" from "{self.path_to_imported_file()}"]'

