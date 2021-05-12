""" This module contains the parser class that
parses *.tex files and tosses away all information not relevant for the later
compilation and linking steps of *.stexobj files.

This parses therefore doesn't just parse the *.tex files but also filters and
preparses the contents in order to create an intermediate parse tree.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import (Any, Callable, Collection, Dict, List, Optional, Sequence,
                    Set, Tuple, Union)

from .. import vscode
from ..util import roman_numerals
from ..latex import parser
from . import exceptions, symbols, util

__all__ = (
    'IntermediateParser',
    'IntermediateParseTree',
    'TokenWithLocation',
    'ScopeIntermediateParseTree',
    'ModsigIntermediateParseTree',
    'ModnlIntermediateParseTree',
    'ModuleIntermediateParseTree',
    'TrefiIntermediateParseTree',
    'DefiIntermediateParseTree',
    'SymIntermediateParserTree',
    'SymdefIntermediateParseTree',
    'ImportModuleIntermediateParseTree',
    'GImportIntermediateParseTree',
    'GStructureIntermediateParseTree',
    'ViewIntermediateParseTree',
    'ViewSigIntermediateParseTree',
    'TassignIntermediateParseTree',
)


class IntermediateParseTree:
    ' Base class for a parse tree specializations. '

    def __init__(self, location: vscode.Location):
        self.location = location
        self.children: List[IntermediateParseTree] = []
        self.parent: Optional[IntermediateParseTree] = None

    def add_child(self, child: IntermediateParseTree):
        assert child.parent is None
        self.children.append(child)
        child.parent = self

    def find_parent_module_name(self) -> Optional[str]:
        """ Finds the first intermediate tree that can give us information about in which module we currently
        are and returns the name of that module. This is required because some environments create module symbols
        and already know the real module symbol at the compilation step (like modsig), but some environments only give us information
        about the module name (like bindings).
        """
        if self.parent:
            return self.parent.find_parent_module_name()
        return None

    def find_parent_module_parse_tree(self) -> Optional[IntermediateParseTree]:
        ' Returns the parse tree with information about the parent module name. '
        if self.parent:
            return self.parent.find_parent_module_parse_tree()
        return None

    def gather_imports(self) -> List:
        """ Returns list of information about imported modules.
        Modules specified by gimport and importmodule statements as well as the imported modules
        in view environments.
        """
        if self.parent:
            return self.parent.gather_imports()
        return []

    @property
    def depth(self) -> int:
        if self.parent:
            return self.parent.depth + 1
        return 0

    def traverse(self, enter, exit=None):
        if enter:
            enter(self)
        for c in self.children:
            c.traverse(enter, exit)
        if exit:
            exit(self)


class TokenWithLocation:
    ' Just some container for the text inside range of the file that owns an instance of this class. '

    def __init__(self, text: str, range: vscode.Range):
        self.text = text
        self.range = range

    def __repr__(self):
        return self.text

    @staticmethod
    def parse_oargs(oargs: List[parser.OArgument]) -> Tuple[List[TokenWithLocation], Dict[str, TokenWithLocation]]:
        ' Returns a tuple of a list and a dict of named and unnamed optional latex arguments respectively. '
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
    def from_node(node: parser.Node) -> TokenWithLocation:
        return TokenWithLocation(node.text_inside, node.location.range)

    @staticmethod
    def from_node_union(nodes: Sequence[parser.Node], separator: str = ',') -> Optional[TokenWithLocation]:
        # TODO: Can be deleted?
        tags = list(map(TokenWithLocation.from_node, nodes))
        ranges: Sequence[vscode.Range] = tuple(
            token.range for token in tags)
        range_union = vscode.Range.big_union(ranges)
        assert range_union is not None, "Node ranges union must exist."
        text = tuple(token.text for token in tags)
        return TokenWithLocation(separator.join(text), range_union)


class IntermediateParser:
    " An object contains information about symbols, locations, imports of an stex source file. "

    def __init__(self, path: Path):
        ' Creates an empty container without actually parsing the file. '
        # Path to the source file
        self.path = Path(path)
        # Buffer of all the root environments this file has.
        self.roots: List[IntermediateParseTree] = []
        # Buffer for exceptions raised during parsing
        self.errors: Dict[vscode.Location, List[Exception]] = {}

    def parse(self, content: str = None) -> IntermediateParser:
        ''' Parse the file from the in the constructor given path.

        Parameters:
            content: Currently buffered content of the file that is supposed to be parsed.

        Returns:
            self
        '''
        if self.roots:
            raise ValueError('File already parsed.')
        subclass_constructors: Tuple[Callable[[parser.Environment], Any], ...] = tuple(
            getattr(cls, 'from_environment')
            for cls
            in IntermediateParseTree.__subclasses__()
            if hasattr(cls, 'from_environment')
        )
        try:
            latex_parser = parser.LatexParser(self.path)
            latex_parser.parse(content)
            stack: List[Tuple[Optional[parser.Environment], Callable]] = [
                (None, self.roots.append)]
            latex_parser.walk(
                lambda env: self._enter(env, stack, subclass_constructors),
                lambda env: self._exit(env, stack))
        except (exceptions.CompilerError, parser.LatexException, UnicodeError, FileNotFoundError) as ex:
            self.errors.setdefault(self.default_location, []).append(ex)
        return self

    def _enter(
            self,
            env: parser.Environment,
            stack_of_add_child_operations: List[Tuple[Optional[parser.Environment], Callable]],
            parse_tree_constructors: Collection[Callable[[parser.Environment], Any]]):
        """ Handles entering an environment while walking through the from the parser generated syntax tree.

        Args:
            env (parser.Environment): The current environment.
            stack_of_add_child_operations (List[Tuple[Optional[parser.Environment], Callable]]): A stack that keeps track of
                which environments are currently entered.
                The top if this stack will be used to add the current environment to after it is parased.
            parse_tree_constructors (Collection[Callable[[parser.Environment], Any]]): A collection of constructors
                that generate a IntermediateParseTree subclass instance.
                The first constructor that does not return None will be accepted the correct parsing of the given environment.
        """
        try:
            tree: Optional[IntermediateParseTree] = next(
                filter(
                    # Remove all constructors that returned None because it decided that the parsing of the environment is not it's job.
                    None,
                    # Try out all constructors on the current environment
                    map(
                        lambda from_environment: from_environment(env),
                        parse_tree_constructors)
                    # Return default None if there is no from_environment method
                    # that is responsible for the parsing of this environment
                    # This means that it is some other environment
                    # that has no inpact on the final symbol structure and can be ignored.
                ), None)
            if tree:
                # Get the top stack operation and add this tree as a child
                if stack_of_add_child_operations[-1]:
                    stack_of_add_child_operations[-1][1](tree)
                # Add this parse tree's add_child operation to the top
                stack_of_add_child_operations.append((env, tree.add_child))
                return
            # If this is reached, then the environment will be ignored because it does not have a
            # valid constructor
        except exceptions.CompilerError as e:
            # Reached if there exists a constructor that is responsible,
            # but the construction of the parse tree could not be completed
            self.errors.setdefault(env.location, []).append(e)

    def _exit(self, env, stack_of_add_child_operations: List[Tuple[Optional[parser.Environment], Callable]]):
        if stack_of_add_child_operations[-1][0] == env:
            stack_of_add_child_operations.pop()

    @property
    def default_location(self) -> vscode.Location:
        """ Returns a location with a range that contains the whole file
            or just the range from 0 to 0 if the file can't be openened.
        """
        try:
            content = self.path.read_text()
            lines = content.split('\n')
            num_lines = len(lines)
            len_last_line = len(lines[-1])
            return vscode.Location(self.path.as_uri(), vscode.Range(vscode.Position(0, 0), vscode.Position(num_lines - 1, len_last_line - 1)))
        except Exception:
            return vscode.Location(self.path.as_uri(), vscode.Position(0, 0))


class ScopeIntermediateParseTree(IntermediateParseTree):
    ' A scope is a new scope that seperates import statements from each other and prevent being imported from another file. '
    PATTERN = re.compile(r'n?omtext|example|omgroup|frame')

    def __init__(self, location: vscode.Location, scope_name: TokenWithLocation):
        super().__init__(location)
        self.scope_name = scope_name

    @classmethod
    def from_environment(cls, e: parser.Environment) -> Optional[ScopeIntermediateParseTree]:
        match = ScopeIntermediateParseTree.PATTERN.fullmatch(e.env_name)
        if not match:
            return None
        return ScopeIntermediateParseTree(e.location, TokenWithLocation.from_node(e.name))

    def __repr__(self) -> str:
        return f'[Scope "{self.scope_name.text}"]'


class ModsigIntermediateParseTree(IntermediateParseTree):
    PATTERN = re.compile(r'modsig')

    def __init__(self, location: vscode.Location, name: TokenWithLocation):
        super().__init__(location)
        self.name = name

    def find_parent_module_name(self) -> Optional[str]:
        return self.name.text

    def find_parent_module_parse_tree(self):
        return self

    @classmethod
    def from_environment(cls, e: parser.Environment) -> Optional[ModsigIntermediateParseTree]:
        match = ModsigIntermediateParseTree.PATTERN.fullmatch(e.env_name)
        if not match:
            return
        if not e.rargs:
            raise exceptions.CompilerError(
                'Modsig environment missing required argument: {<module name>}')
        return ModsigIntermediateParseTree(
            e.location,
            TokenWithLocation.from_node(e.rargs[0]))

    def __repr__(self):
        return f'[Modsig name={self.name.text}]'


class ModnlIntermediateParseTree(IntermediateParseTree):
    PATTERN = re.compile(r'(mh)?modnl')

    def __init__(
            self,
            location: vscode.Location,
            name: TokenWithLocation,
            lang: TokenWithLocation,
            mh_mode: bool):
        super().__init__(location)
        self.name = name
        self.lang = lang
        self.mh_mode = mh_mode

    def find_parent_module_name(self) -> str:
        return self.name.text

    def find_parent_module_parse_tree(self):
        return self

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
        return (self.location.path.parents[0] / (self.name.text + '.tex'))

    @classmethod
    def from_environment(cls, e: parser.Environment) -> Optional[ModnlIntermediateParseTree]:
        match = ModnlIntermediateParseTree.PATTERN.fullmatch(e.env_name)
        if not match:
            return None
        if len(e.rargs) != 2:
            raise exceptions.CompilerError(
                f'Argument count mismatch (expected 2, found {len(e.rargs)}).')
        return ModnlIntermediateParseTree(
            e.location,
            TokenWithLocation.from_node(e.rargs[0]),
            TokenWithLocation.from_node(e.rargs[1]),
            mh_mode=match.group(1) == 'mh',
        )

    def __repr__(self):
        mh = 'mh' if self.mh_mode else ''
        return f'[{mh}Modnl {self.name.text} lang={self.lang.text}]'


class ViewIntermediateParseTree(IntermediateParseTree):
    # TODO: possibly mhview should be separate -- the same way as module is separated from mhmodnl
    PATTERN = re.compile(r'mhview|gviewnl')

    def __init__(
            self,
            location: vscode.Location,
            env: str,
            # mhview can be anonymous, TODO: check option 'id' field
            module: Optional[TokenWithLocation],
            lang: Optional[TokenWithLocation],
            fromrepos: Optional[TokenWithLocation],
            frompath: Optional[TokenWithLocation],
            torepos: Optional[TokenWithLocation],
            topath: Optional[TokenWithLocation],
            source_module: TokenWithLocation,
            target_module: TokenWithLocation):
        super().__init__(location)
        self.env = env
        self.module = module
        self.lang = lang
        self.fromrepos = fromrepos
        self.frompath = frompath
        self.torepos = torepos
        self.topath = topath
        self.source_module = source_module
        self.target_module = target_module

    def find_parent_module_name(self):
        return self.module.text

    @classmethod
    def from_environment(cls, e: parser.Environment) -> Optional[ViewIntermediateParseTree]:
        match = cls.PATTERN.fullmatch(e.env_name)
        if not match:
            return None
        _, named = TokenWithLocation.parse_oargs(e.oargs)
        module = None
        lang = None
        if e.env_name == 'gviewnl':
            if len(e.rargs) < 4:
                raise exceptions.CompilerError(
                    f'Argument count mismatch: gviewnl requires 4 arguments, found {len(e.rargs)}.')
            for illegal_arg in ['frompath', 'topath']:
                if illegal_arg in named:
                    raise exceptions.CompilerError(
                        f'{illegal_arg} argument not allowed in gviewnl.')
            module = TokenWithLocation.from_node(e.rargs[0])
            lang = TokenWithLocation.from_node(e.rargs[1])
        elif e.env_name == 'mhview':
            if len(e.rargs) < 2:
                raise exceptions.CompilerError(
                    f'Argument count mismatch: mhview requires 2 arguments, found {len(e.rargs)}.')
        else:
            raise exceptions.CompilerError(
                f'Invalid environment name "{e.env_name}"')
        return ViewIntermediateParseTree(
            location=e.location,
            env=e.env_name,
            module=module,
            lang=lang,
            fromrepos=named.get('fromrepos'),
            frompath=named.get('frompath'),
            torepos=named.get('torepos'),
            topath=named.get('topath'),
            source_module=TokenWithLocation.from_node(e.rargs[-2]),
            target_module=TokenWithLocation.from_node(e.rargs[-1]),
        )


class ViewSigIntermediateParseTree(IntermediateParseTree):
    PATTERN = re.compile('gviewsig')

    def __init__(
            self,
            location: parser.Location,
            fromrepos: Optional[TokenWithLocation],
            torepos: Optional[TokenWithLocation],
            module: TokenWithLocation,
            source_module: TokenWithLocation,
            target_module: TokenWithLocation):
        super().__init__(location)
        self.fromrepos = fromrepos
        self.torepos = torepos
        self.module = module
        self.source_module = source_module
        self.target_module = target_module

    def find_parent_module_name(self):
        return self.module.text

    @classmethod
    def from_environment(cls, e: parser.Environment) -> Optional[ViewSigIntermediateParseTree]:
        match = ViewSigIntermediateParseTree.PATTERN.fullmatch(e.env_name)
        if not match:
            return None
        if len(e.rargs) < 3:
            raise exceptions.CompilerError(
                f'viewsig requires at least three arguments, found {len(e.rargs)}.')
        _, named = TokenWithLocation.parse_oargs(e.oargs)
        return ViewSigIntermediateParseTree(
            location=e.location,
            fromrepos=named.get('fromrepos', None),
            torepos=named.get('torepos', None),
            module=TokenWithLocation.from_node(e.rargs[0]),
            source_module=TokenWithLocation.from_node(e.rargs[1]),
            target_module=TokenWithLocation.from_node(e.rargs[2]),
        )

    def __repr__(self) -> str:
        return f'[ViewSig "{self.module}" from "{self.fromrepos}" with source "{self.source_module}" and target "{self.target_module}"]'


class ModuleIntermediateParseTree(IntermediateParseTree):
    PATTERN = re.compile(r'(module(\*)?)|(smentry)')

    def __init__(
            self,
            location: vscode.Location,
            id: Optional[TokenWithLocation]):
        super().__init__(location)
        self.id = id

    def find_parent_module_name(self):
        return self.id.text

    def find_parent_module_parse_tree(self):
        return self

    def __repr__(self):
        module = f'id="{self.id.text}"' if self.id else '<anonymous>'
        return f'[Module {module}]'

    @classmethod
    def from_environment(cls, e: parser.Environment) -> Optional[ModuleIntermediateParseTree]:
        match = cls.PATTERN.fullmatch(e.env_name)
        if match is None:
            return None
        _, named = TokenWithLocation.parse_oargs(e.oargs)
        return ModuleIntermediateParseTree(
            location=e.location,
            id=named.get('id'),
        )


class GStructureIntermediateParseTree(IntermediateParseTree):
    PATTERN = re.compile(r'gstructure(\*)?')

    def __init__(self, location: vscode.Location, mhrepos: TokenWithLocation, module: TokenWithLocation):
        super().__init__(location)
        self.mhrepos = mhrepos
        self.module = module

    @classmethod
    def from_environment(cls, e: parser.Environment) -> Optional[GStructureIntermediateParseTree]:
        match = cls.PATTERN.fullmatch(e.env_name)
        if match is None:
            return None
        if len(e.rargs) != 2:
            raise exceptions.CompilerError(
                f'gstructure environment requires at least 2 Arguments but {len(e.rargs)} found.')
        _, named = TokenWithLocation.parse_oargs(e.oargs)
        return GStructureIntermediateParseTree(
            location=e.location,
            mhrepos=named.get('mhrepos'),
            module=TokenWithLocation.from_node(e.rargs[1])
        )

    def __repr__(self) -> str:
        return f'[GStructure "{self.module}"]'


class DefiIntermediateParseTree(IntermediateParseTree):
    PATTERN = re.compile(r'([ma]*)(d|D)ef([ivx]+)(s)?(\*)?')

    def __init__(
            self,
            location: vscode.Location,
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
            raise exceptions.CompilerError(
                f'Defi argument count mismatch: Expected {i + int(a)} vs actual {len(tokens)}.')

    @property
    def name(self) -> str:
        if self.name_annotation:
            return self.name_annotation.text
        if self.a:
            return '-'.join(t.text for t in self.tokens[1:])
        return '-'.join(t.text for t in self.tokens)

    @classmethod
    def from_environment(cls, e: parser.Environment) -> Optional[DefiIntermediateParseTree]:
        match = DefiIntermediateParseTree.PATTERN.fullmatch(e.env_name)
        if match is None:
            return None
        if not e.rargs:
            raise exceptions.CompilerError(
                'Argument count mismatch (expected at least 1, found 0).')
        _, named = TokenWithLocation.parse_oargs(e.oargs)
        try:
            i = roman_numerals.roman2int(match.group(3))
        except:
            raise exceptions.CompilerError(
                f'Invalid environment (are the roman numerals correct?): {e.env_name}')
        return DefiIntermediateParseTree(
            location=e.location,
            tokens=list(map(TokenWithLocation.from_node, e.rargs)),
            name_annotation=named.get('name'),
            m='m' in match.group(1),
            a='a' in match.group(1),
            capital=match.group(2) == 'D',
            i=i,
            s=match.group(4) is not None,
            asterisk=match.group(5) is not None)

    def __repr__(self):
        return f'[Def{"i"*self.i} "{self.name}"]'


class TrefiIntermediateParseTree(IntermediateParseTree):
    PATTERN = re.compile(r'([ma]*)(d|D|t|T)ref([ivx]+)(s)?(\*)?')

    def __init__(
            self,
            location: vscode.Location,
            tokens: List[TokenWithLocation],
            target_annotation: Optional[TokenWithLocation],
            m: bool,
            a: bool,
            capital: bool,
            drefi: bool,
            i: int,
            s: bool,
            asterisk: bool):
        super().__init__(location)
        self.tokens = tokens
        self.target_annotation = target_annotation
        self.m = m
        self.a = a
        self.capital = capital
        self.drefi = drefi
        self.i = i
        self.s = s
        self.asterisk = asterisk
        if i + int(a) != len(tokens):
            raise exceptions.CompilerError(
                f'Trefi argument count mismatch: Expected {i + int(a)} vs. actual {len(tokens)}.')

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
                    return left  # return left in case of <module>?<symbol>
                return None  # return None in case of ?symbol
            # return the whole thing in case of [module]
            return self.target_annotation
        return None  # return None if no oargs are given

    @classmethod
    def from_environment(cls, e: parser.Environment) -> Optional[TrefiIntermediateParseTree]:
        match = TrefiIntermediateParseTree.PATTERN.fullmatch(e.env_name)
        if match is None:
            return None
        if not e.rargs:
            raise exceptions.CompilerError(
                'Argument count mismatch (expected at least 1, found 0).')
        if len(e.unnamed_args) > 1:
            raise exceptions.CompilerError(
                f'Too many unnamed oargs in trefi: Expected are at most 1, found {len(e.unnamed_args)}')
        annotations = (
            TokenWithLocation.from_node(e.unnamed_args[0])
            if e.unnamed_args
            else None
        )
        tokens = list(map(TokenWithLocation.from_node, e.rargs))
        try:
            i = roman_numerals.roman2int(match.group(3))
        except:
            raise exceptions.CompilerError(
                f'Invalid environment (are the roman numerals correct?): {e.env_name}')
        return TrefiIntermediateParseTree(
            location=e.location,
            tokens=tokens,
            target_annotation=annotations,
            m='m' in match.group(1),
            a='a' in match.group(1),
            capital=match.group(2) == 'T',
            drefi=match.group(2) in ('d', 'D'),
            i=i,
            s=match.group(4) is not None,
            asterisk=match.group(5) is not None,
        )

    def __repr__(self):
        module = f' from "{self.module}"' if self.module else ""
        return f'[Tref{"i"*self.i} "{self.name}"{module}]'


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


class SymIntermediateParserTree(IntermediateParseTree):
    PATTERN = re.compile(r'sym([ivx]+)(\*)?')

    def __init__(
            self,
            location: vscode.Location,
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
            raise exceptions.CompilerError(
                f'Symi argument count mismatch: Expected {i} vs actual {len(tokens)}.')

    @property
    def name(self) -> str:
        return '-'.join(token.text for token in self.tokens)

    @classmethod
    def from_environment(cls, e: parser.Environment) -> Optional[SymIntermediateParserTree]:
        match = SymIntermediateParserTree.PATTERN.fullmatch(e.env_name)
        if match is None:
            return None
        if not e.rargs:
            raise exceptions.CompilerError(
                'Argument count mismatch (expected at least 1, found 0).')
        unnamed, named = TokenWithLocation.parse_oargs(e.oargs)
        try:
            i = roman_numerals.roman2int(match.group(1))
        except Exception as err:
            raise exceptions.CompilerError(
                f'Invalid environment (are the roman numerals correct?): {e.env_name}') from err
        return SymIntermediateParserTree(
            location=e.location,
            tokens=list(map(TokenWithLocation.from_node, e.rargs)),
            unnamed_args=unnamed,
            named_args=named,
            i=i,
            asterisk=match.group(2) is not None,
        )

    def __repr__(self):
        return f'[Sym{"i"*self.i}{"*"*self.asterisk} "{self.name}"]'


class SymdefIntermediateParseTree(IntermediateParseTree):
    PATTERN = re.compile(r'symdef(\*)?')

    def __init__(
            self,
            location: vscode.Location,
            name: TokenWithLocation,
            unnamed_oargs: List[TokenWithLocation],
            named_oargs: Dict[str, TokenWithLocation],
            asterisk: bool):
        super().__init__(location)
        self.name: TokenWithLocation = name
        self.noverb = _NoverbHandler(unnamed_oargs, named_oargs)
        self.asterisk: bool = asterisk

    @classmethod
    def from_environment(cls, e: parser.Environment) -> Optional[SymdefIntermediateParseTree]:
        match = SymdefIntermediateParseTree.PATTERN.fullmatch(e.env_name)
        if match is None:
            return None
        if not e.rargs:
            raise exceptions.CompilerError(
                'Argument count mismatch: At least one argument required.')
        name = TokenWithLocation.from_node(e.rargs[0])
        unnamed, named = TokenWithLocation.parse_oargs(e.oargs)
        return SymdefIntermediateParseTree(
            location=e.location,
            name=named.get('name', name),
            unnamed_oargs=unnamed,
            named_oargs=named,
            asterisk=match.group(1) is not None,
        )

    def __repr__(self):
        return f'[Symdef{"*"*self.asterisk} "{self.name.text}"]'


class ImportModuleIntermediateParseTree(IntermediateParseTree):
    PATTERN = re.compile(r'(import|use)(mh)?module(\*)?')

    def __init__(
            self,
            location: vscode.Location,
            module: TokenWithLocation,
            mhrepos: Optional[TokenWithLocation],
            repos: Optional[TokenWithLocation],
            dir: Optional[TokenWithLocation],
            load: Optional[TokenWithLocation],
            path: Optional[TokenWithLocation],
            export: bool,
            mh_mode: bool,
            asterisk: bool):
        super().__init__(location)
        self.module = module
        self.mhrepos = mhrepos
        self.repos = repos
        self.dir = dir
        self.load = load
        self.path = path
        self.export = export
        self.mh_mode = mh_mode
        self.asterisk = asterisk
        if len(list(self.location.path.parents)) < 4:
            raise exceptions.CompilerWarning(
                f'Unable to compile module with a path depth of less than 4: {self.location.path}')
        if mh_mode:
            # mhimport{}
            # mhimport[dir=..]{}
            # mhimport[path=..]{}
            # mhimport[mhrepos=..,dir=..]{}
            # mhimport[mhrepos=..,path=..]{}
            if dir and path:
                raise exceptions.CompilerError(
                    'Invalid argument configuration in importmhmodule: "dir" and "path" must not be specified at the same time.')
            if mhrepos and not (dir or path):
                raise exceptions.CompilerError(
                    'Invalid argument configuration in importmhmodule: "mhrepos" requires a "dir" or "path" argument.')
            elif load:
                raise exceptions.CompilerError(
                    'Invalid argument configuration in importmhmodule: "load" argument must not be specified.')
        elif mhrepos or dir or path:
            raise exceptions.CompilerError(
                'Invalid argument configuration in importmodule: "mhrepos", "dir" or "path" must not be specified.')
        elif not load:
            # import[load=..]{}
            raise exceptions.CompilerError(
                'Invalid argument configuration in importmodule: Missing "load" argument.')

    @staticmethod
    def build_path_to_imported_module(
            root: Path,
            current_file: Path,
            mhrepo: Optional[str],
            path: Optional[str],
            dir: Optional[str],
            load: Optional[str],
            module: str):
        """ Reconstructs the path to the module imported by a Import statement. (Warning: not gimport!)

        Parameters:
            root: The mathhub root directory.
            current_file: File where the import statement is located in.
            mhrepo: Optional latex environment argument mhrepo=
            path: Optional latex environment argument path=
            dir: Optional latex environment argument dir=
            load: Optional latex environment argument load=
            module: The module name extracted from the required latex arguments.
        """
        if load:
            return (root / load / (module + '.tex')).expanduser().resolve().absolute()
        if not mhrepo and not path and not dir:
            return (current_file).expanduser().resolve().absolute()
        if mhrepo:
            source: Path = root / mhrepo / 'source'
        else:
            source: Path = util.find_source_dir(root, current_file)
        if dir:
            result = source / dir / (module + '.tex')
        elif path:
            result = source / (path + '.tex')
        else:
            raise ValueError(
                'Invalid arguments: "path" or "dir" must be specified if "mhrepo" is.')
        return result.expanduser().resolve().absolute()

    def path_to_imported_file(self, root: Path) -> Path:
        ' Calls the classmethod build_path_to_imported_module with information from this instance. '
        return ImportModuleIntermediateParseTree.build_path_to_imported_module(
            root,
            self.location.path,
            self.mhrepos.text if self.mhrepos else None,
            self.path.text if self.path else None,
            self.dir.text if self.dir else None,
            self.load.text if self.load else None,
            self.module.text)

    def __repr__(self):
        try:
            from_ = f' from "{self.path_to_imported_file(Path.cwd())}"'
        except:
            from_ = ''
        access = symbols.AccessModifier.PUBLIC if self.export else symbols.AccessModifier.PRIVATE
        return f'[{access.value} ImportModule "{self.module.text}"{from_}]'

    @classmethod
    def from_environment(cls, e: parser.Environment) -> Optional[ImportModuleIntermediateParseTree]:
        match = ImportModuleIntermediateParseTree.PATTERN.fullmatch(e.env_name)
        if match is None:
            return None
        if len(e.rargs) != 1:
            raise exceptions.CompilerError(
                f'Argument count mismatch: Expected exactly 1 argument but found {len(e.rargs)}')
        module = TokenWithLocation.from_node(e.rargs[0])
        _, named = TokenWithLocation.parse_oargs(e.oargs)
        return ImportModuleIntermediateParseTree(
            location=e.location,
            module=module,
            mhrepos=named.get('mhrepos') or named.get('repos'),
            repos=named.get('repos'),
            dir=named.get('dir'),
            path=named.get('path'),
            load=named.get('load'),
            export=match.group(1) == 'import',
            mh_mode=match.group(2) == 'mh',
            asterisk=match.group(3) == '*'
        )


class GImportIntermediateParseTree(IntermediateParseTree):
    PATTERN = re.compile(r'g(import|use)(\*)?')

    def __init__(
            self,
            location: vscode.Location,
            module: TokenWithLocation,
            repository: Optional[TokenWithLocation],
            export: bool,
            asterisk: bool):
        super().__init__(location)
        self.module = module
        self.repository = repository
        self.export = export
        self.asterisk = asterisk

    @staticmethod
    def build_path_to_imported_module(
            root: Path,
            current_file: Path,
            repo: Optional[Union[Path, str]],
            module: str) -> Path:
        """ A static helper method to get the targeted filepath by a gimport environment.

        Parameters:
            root: Root of mathhub.
            current_file: File which uses the gimport statement.
            repo: Optional repository specified in gimport statements: gimport[<repository>]{...}
            module: The targeted module in gimport statements: gimport{<module>}

        Returns:
            Path to the file in which the module <module> is located.
        """
        if repo is not None:
            assert current_file.relative_to(root)
            source = root / repo / 'source'
        else:
            # TODO: What is the path to imported module if repo in gimport[repo] is not given?
            source = current_file.parent
        path = (source / module).with_suffix('.tex')
        return path.expanduser().resolve().absolute()

    def path_to_imported_file(self, root: Path) -> Path:
        ''' Returns the path to the module file this gimport points to. '''
        return GImportIntermediateParseTree.build_path_to_imported_module(
            root=root,
            current_file=self.location.path,
            repo=self.repository.text.strip() if self.repository else None,
            module=self.module.text.strip())

    @classmethod
    def from_environment(cls, e: parser.Environment) -> Optional[GImportIntermediateParseTree]:
        match = GImportIntermediateParseTree.PATTERN.fullmatch(e.env_name)
        if match is None:
            return None
        if len(e.rargs) != 1:
            raise exceptions.CompilerError(
                f'Argument count mismatch (expected 1, found {len(e.rargs)}).')
        module = TokenWithLocation.from_node(e.rargs[0])
        unnamed, _ = TokenWithLocation.parse_oargs(e.oargs)
        if len(unnamed) > 1:
            raise exceptions.CompilerError(
                f'Optional argument count mismatch (expected at most 1, found {len(e.oargs)})')
        return GImportIntermediateParseTree(
            location=e.location,
            module=module,
            repository=next(iter(unnamed), None),
            export=match.group(1) == 'import',
            asterisk=match.group(2) is not None,
        )

    def __repr__(self):
        try:
            from_ = f' from "{self.path_to_imported_file(Path.cwd())}"'
        except Exception:
            from_ = ''
        access = symbols.AccessModifier.PUBLIC if self.export else symbols.AccessModifier.PRIVATE
        return f'[{access.value} gimport{"*"*self.asterisk} "{self.module.text}"{from_}]'


class TassignIntermediateParseTree(IntermediateParseTree):
    PATTERN = re.compile(r'(?P<at>[tv])assign(?P<asterisk>\*?)')

    def __init__(
            self,
            location: vscode.Location,
            torv: str,
            source_symbol: TokenWithLocation,
            target_term: TokenWithLocation,
            asterisk: bool):
        super().__init__(location)
        self.torv = torv
        self.source_symbol = source_symbol
        self.target_term = target_term
        self.asterisk = asterisk

    @classmethod
    def from_environment(cls, e: parser.Environment) -> Optional[TassignIntermediateParseTree]:
        match = TassignIntermediateParseTree.PATTERN.fullmatch(e.env_name)
        if match is None:
            return None
        if len(e.rargs) != 2:
            raise exceptions.CompilerError(
                f'Argument count mismatch (expected 2, found {len(e.rargs)}).')
        source_symbol = TokenWithLocation.from_node(e.rargs[0])
        target_term = TokenWithLocation.from_node(e.rargs[1])
        if len(e.oargs) > 0:
            raise exceptions.CompilerError('Unexpected optional arguments.')
        return TassignIntermediateParseTree(
            location=e.location,
            torv=match.group('at'),
            source_symbol=source_symbol,
            target_term=target_term,
            asterisk=match.group('asterisk') is not None,
        )
