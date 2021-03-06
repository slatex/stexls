from __future__ import annotations

import re
import tempfile
from pathlib import Path
from typing import (Callable, Dict, Iterator, List, Optional, Pattern, Tuple,
                    Union)

import antlr4
from antlr4.error.ErrorListener import ErrorListener
from stexls.util.unwrap import unwrap
from stexls.vscode import Location, Position, Range

from .grammar.out.LatexLexer import LatexLexer as _LatexLexer
from .grammar.out.LatexParser import LatexParser as _LatexParser
from .grammar.out.LatexParserListener import \
    LatexParserListener as _LatexParserListener

__all__ = ['LatexParser', 'InlineEnvironment', 'Environment',
           'Token', 'MathToken', 'Node', 'SyntaxErrorException', 'LatexException']


class SyntaxErrorException(Exception):
    pass


class LatexException(Exception):
    pass


def _get_ctx_range(ctx):
    if not ctx.start or not ctx.stop:
        raise LatexException(
            'Invalid context encountered during parsing of latex file.')
    return ctx.start.start, ctx.stop.stop + 1


class Node:
    """ Base class for the syntax tree content.

    Attributes:
        parser (LatexParser): The parser this node belongs to.
        begin (int): Index of the first character that belongs to this node.
        end (int): Index of the last character that belongs to this node.
        children: List[Node]: List of all children.
            Node metadata like optional arguments are stored separately and are not children.
        _parent (Node, optional): Parent node this node belongs to.
            Accessed via the `parent` property getter.
    """

    def __init__(self, parser: LatexParser, begin: int, end: int):
        """ Creates a node.

        Args:
            parser (LatexParser): Parser that generated this node.
            begin (int): Zero indexed begin offset in the source file.
            end (int): Zero indexed end offset in the source file.
        """
        assert isinstance(end, int)
        assert isinstance(begin, int)
        self.parser = parser
        self.begin: int = begin
        self.end: int = end
        self.children: List[Node] = []
        self._parent: Optional[Node] = None

    def get_scope(self, filter: Optional[Pattern] = None) -> Location:
        ' Returns the largest scope this is contained in. Use the filter to filter out environment names that constitute a scope. '
        if not self._parent or (isinstance(self, Environment) and (not filter or filter.match(self.env_name))):
            return Location(
                Path(self.parser.file).as_uri(),
                Range(
                    self.parser.offset_to_position(self.begin),
                    self.parser.offset_to_position(self.end)))
        return self._parent.get_scope(filter)

    @property
    def parent(self) -> Optional[Node]:
        return self._parent

    @parent.setter
    def parent(self, value: Node):
        if self._parent is not None:
            raise RuntimeError(
                f'Unable to assign parent {value} to {self}: Parent alredy assigned to {self.parent}')
        self._parent = value

    @property
    def location(self) -> Location:
        " Location of this node in the file. "
        return Location(Path(self.parser.file).as_uri(), self.range)

    @property
    def range(self) -> Range:
        " Converts the begin and end offsets to a vscode.Range "
        begin = self.parser.offset_to_position(self.begin)
        end = self.parser.offset_to_position(self.end)
        return Range(begin, end)

    @property
    def content_range(self) -> Range:
        " Range of the children of this node. Range of self if there are no children. "
        if not self.children:
            return self.range
        begin = self.parser.offset_to_position(self.children[0].begin)
        end = self.parser.offset_to_position(self.children[-1].end)
        return Range(begin, end)

    @property
    def text(self) -> str:
        ' Returns the text inside begin and end offset. '
        return self.parser.get_text_by_offset(self.begin, self.end)

    @property
    def text_inside(self) -> str:
        ''' Get text spanned by first and last child nodes.

        Equal to self.text if there are no children.
        '''
        if not self.children:
            return self.text
        start = self.children[0].begin
        stop = self.children[-1].end
        return self.parser.get_text_by_offset(start, stop)

    def add(self, node: Node):
        ' Adds a child. '
        node.parent = self
        self.children.append(node)

    @property
    def tokens(self) -> Iterator[Token]:
        ' Iterator that iterates through all tokens of all children recursively. '
        for child in self.children:
            yield from child.tokens

    @property
    def envs(self) -> Tuple[str, ...]:
        ' Lists all PARENT environments this node is contained in. '
        env = (self.env_name,) if self.env_name else ()
        if not self.parent:
            return env
        return self.parent.envs + env

    @property
    def env_name(self) -> Optional[str]:
        ' The environment name of this node. None if this node is not an environment. '
        return None

    def finditer(self, env_pattern: Pattern) -> Iterator[Node]:
        ' Iterator with only the nodes with environments that match the given pattern. '
        for child in self.children:
            yield from child.finditer(env_pattern)

    @classmethod
    def from_ctx(cls, ctx: antlr4.ParserRuleContext, parser, **kwargs):
        range = _get_ctx_range(ctx)
        return cls(parser, *range, **kwargs)

    def __repr__(self):
        return f'[Node "{self.text.strip()}"]'


class Token(Node):
    ' A token is a leaf node that contains the actual text of the source file. '

    def __init__(self, parser: LatexParser, begin: int, end: int, lexeme: str):
        """ Constructs a token with text and position information.
        Parameters:
            begin: Zero indexed begin offset of the text.
            end: Zero indexed end offset of the text.
            lexeme: The actual text in the source document.
        """
        super().__init__(parser, begin, end)
        self.lexeme = lexeme

    @property
    def tokens(self):
        yield self

    def add(self, child):
        ' Tokens can not have children. '
        raise RuntimeError("Tokens can not add children.")

    def __repr__(self):
        return f'[Token begin={self.begin} end={self.end} "{self.lexeme.strip()}"]'


class OArgument(Node):
    def __init__(self, parser: LatexParser, begin: int, end: int):
        super().__init__(parser, begin, end)
        self.name: Optional[Node] = None
        self.value: Optional[Node] = None

    @property
    def tokens(self):
        yield from ()

    def add_value(self, value: Node):
        if self.value is not None:
            raise ValueError('OArgument already has a value assigned.')
        value.parent = self
        self.value = value

    def add_name(self, name: Node):
        if self.name is not None:
            raise ValueError('OArgument already has a name assigned.')
        name.parent = self
        self.name = name

    def __repr__(self):
        if self.name:
            return f'[OArg name={self.name} value={self.value}]'
        return f'[OArg value={self.value}]'


class MathToken(Token):
    ' A special token that represents an environment that contains math. '
    @property
    def env_name(self):
        return '$'


class Environment(Node):
    """ An environment is a node of the form
        \\begin{name}[<oargs>]{<rargs>}
            <text>
        \\end{name}
        The oargs and rargs do not contain text.
    """

    def __init__(self, parser: LatexParser, begin: int, end: int):
        """ Initializes an environment node with an empty name and empty rarg & oarg arrays.

        The name attribute is a token with the location information of where the string which
        constitutes the name of this environment is located.

        "RArg array" stands for "Required Argument Array" and is the list of arguments in curly braces "{...rargs}".
        "OArg array" stands for "Optional Argument Array" and is the optional list of arguments in square brackets "[...orgs]".

        Parameters:
            begin: Zero indexed begin offset of where the environment's first character is (the first "\\")
            end: Zero indexed end offset of where the environment's last character is (usually a "}")
        """
        super().__init__(parser, begin, end)
        self.oargs: List[OArgument] = []
        self.rargs: List[Node] = []
        self.name: Optional[Node] = None

    @property
    def unnamed_args(self) -> List[Node]:
        return [
            unwrap(oarg.value)
            for oarg in self.oargs
            if oarg.name is None
        ]

    @property
    def named_args(self) -> Dict[str, Node]:
        return {
            oarg.name.text: unwrap(oarg.value)
            for oarg in self.oargs
            if oarg.name is not None
        }

    def add_oarg(self, oarg: OArgument):
        ' Registers an OArg. '
        oarg.parent = self
        self.oargs.append(oarg)

    def add_rarg(self, rarg: Node):
        ' Registers an RArg. '
        rarg.parent = self
        self.rargs.append(rarg)

    def add_name(self, name: Node):
        ' Adds a token as a name provider. '
        if self.name is not None:
            raise ValueError('Environment already has a name provider token.')
        name.parent = self
        self.name = name

    @property
    def env_name(self) -> str:
        """ Gets the environment's name from the provided name token,
            raises if no token provided.
        """
        if self.name is None:
            raise ValueError(
                'Unable to get environment name,'
                'because no name token was provided.')
        return self.name.text_inside.strip()

    @property
    def tokens(self):
        ' Returns tokens that are neither OArg nor RArgs. '
        for child in self.children:
            if child in self.oargs or child in self.rargs:
                continue
            yield from child.tokens

    def finditer(self, env_pattern: Pattern) -> Iterator[Node]:
        if self.name and re.fullmatch(env_pattern, self.name.text):
            yield self
        else:
            yield from super().finditer(env_pattern)

    def __repr__(self):
        return f'[Environment name={self.name}]'


class InlineEnvironment(Environment):
    """ Same as an environment except that the RArguments of the
        environment contain the text.
        Written something like:
        \\name[<oargs>]{<rarg>}{<rarg>}

        Tokens yielded from inline environments
        are the tokens from <rarg>s.
    """
    @property
    def tokens(self):
        ' Inline environments only have public tokens in their rargs. '
        for arg in self.rargs:
            yield from arg.tokens

    def add_rarg(self, rarg: Node):
        super().add_rarg(rarg)
        # TODO: Not sure if adding rargs to the rarg and child array will break something...
        self.children.append(rarg)


class LatexParser:
    def __init__(self, file: Union[str, Path], encoding: str = 'utf-8'):
        """ Reads and parses the given file using latex syntax.

        Loads the given file and stores the text in self.source.
        The text is parsed and the result is stored in self.root.
        Syntax errors which occured during parsing are also
        retrievable using self.syntax_errors.

        Args:
            file (Union[str, Path]): Path to a file.
            encoding (str): Encoding of the file. Defaults to 'utf-8'.
        """
        self.file: Path = Path(file).absolute()
        self.encoding: str = encoding
        self.source: Optional[str] = None
        self.root: Optional[Node] = None
        self.syntax_errors: List[Tuple[Location, Exception]] = []
        self.parsed = False

    def parse(self, content: Optional[str] = None) -> Node:
        """ Actually parses the file given in the constructor.

        Parameters:
            content (str, optional): Optional content of the file. If None, then the file is read from disk with open.

        Returns:
            The root node of the parsed file.
        """
        self.parsed = True
        if content is None:
            with open(self.file, encoding=self.encoding) as fd:
                self.source = fd.read()
        else:
            self.source = content
        self._line_lengths = [
            len(line) + 1
            for line
            in self.source.split('\n')
        ]
        input_stream = antlr4.InputStream(self.source)
        lexer = _LatexLexer(input_stream)
        lexer.removeErrorListeners()
        stream = antlr4.CommonTokenStream(lexer)
        parser = _LatexParser(stream)
        parser.removeErrorListeners()
        error_listener = _SyntaxErrorErrorListener(self.file)
        parser.addErrorListener(error_listener)
        listener = Listener(self)
        walker = antlr4.ParseTreeWalker()
        parse_tree = parser.main()
        walker.walk(listener, parse_tree)
        self.syntax_errors.extend(error_listener.syntax_errors)
        self.root = listener.stack[0]
        return self.root

    @staticmethod
    def from_source(source: str) -> LatexParser:
        """ Parses the text from source.

        The source is stored inside a temporary file
        before being given to the parser.

        Args:
            source (str): Source text.

        Returns:
            LatexParser: Parser for the source.
        """
        with tempfile.NamedTemporaryFile(suffix='.tex', encoding='utf-8', delete=False, mode='w') as fd:
            fd.write(source)
            fd.flush()
        return LatexParser(file=Path(fd.name), encoding='utf-8')

    def offset_to_position(self, offset: int) -> Position:
        """ Converts offset to tuple of line and character.

        Args:
            offset (int): 0-indexed offset character in the file.

        Returns:
            Position: Equivalent position.
        """
        i = 0
        for i, line_len in enumerate(self._line_lengths):
            if offset < line_len:
                break
            offset -= line_len
        return Position(i, offset)

    def position_to_offset(self, line: int, character: int) -> int:
        """ Converts 0-indexed line and 0-indexed character to an offset.

        Args:
            line (int): 0-indexed line or Position.
            character (int): 0-indexed character of that line.

        Returns:
            int: 0-indexed offset of that line and character.
        """
        return sum(self._line_lengths[:line]) + character

    def get_text_by_offset(self, begin: int, end: int) -> str:
        """ Gets the text between begin and end offset.

        Args:
            begin (int): 0-indexed character begin offset (inclusive).
            end (int): 0-indexed character end offset (exclusive).

        Returns:
            str: String inside the given range.
        """
        assert self.source is not None, '"source" must not be None'
        return self.source[begin:end]

    def walk(self, enter: Callable[[Environment], None], exit: Callable[[Environment], None] = None):
        """ Walks through environments, calling enter() and exit() on each.

        Args:
            enter (Callable[[Environment], None]): Called the first time the environment is encountered.
            exit (Callable[[Environment], None], optional):
                Called when all children of a previously entered environment have been visited.
                Defaults to None.
        """
        stack = [self.root]
        visited = []
        while stack:
            current = stack.pop()
            if isinstance(current, Environment):
                if current in visited:
                    if exit is not None:
                        exit(current)
                else:
                    enter(current)
                    stack.append(current)
                    stack.extend(reversed(current.children))
                    visited.append(current)
            elif current is not None:
                stack.extend(current.children)
            else:
                raise RuntimeError('"current" is None')


class _SyntaxErrorErrorListener(ErrorListener):
    ' Error listener that captures syntax errors during parsing. '

    def __init__(self, file: Union[str, Path]):
        """ Initializes the error listener with the filename which is to be parsed.

        Args:
            file (str): Filename
        """
        super().__init__()
        self.file = Path(file)
        self.syntax_errors: List[Tuple[Location, SyntaxErrorException]] = []

    def syntaxError(self, recognizer, offendingSymbol, line, column, msg, e):
        position = Position(line, column)
        location = Location(self.file.absolute().as_uri(), position)
        exception = SyntaxErrorException(msg)
        self.syntax_errors.append((location, exception))


class Listener(_LatexParserListener):
    ' Implements the antlr4 methods for parsing a latex file. '

    def __init__(self, parser: LatexParser):
        super().__init__()
        self.parser = parser
        self.stack: List[Node] = []

    def enterMain(self, ctx: _LatexParser.MainContext):
        self.stack.append(Node.from_ctx(ctx, self.parser))

    def exitMain(self, ctx: _LatexParser.MainContext):
        if len(self.stack) != 1:
            env = self.stack.pop()
            error = LatexException(f'Environment not closed: {env}')
            self.parser.syntax_errors.append((env.location, error))

    def exitMath(self, ctx: _LatexParser.MathContext):
        lexeme = str(ctx.MATH_ENV())
        node = MathToken.from_ctx(ctx, self.parser, lexeme=lexeme)
        self.stack[-1].add(node)

    def enterBody(self, ctx: _LatexParser.BodyContext):
        if ctx.body():
            node = Node.from_ctx(ctx, self.parser)
            self.stack.append(node)

    def exitBody(self, ctx: _LatexParser.BodyContext):
        if ctx.body():
            body = self.stack.pop()
            self.stack[-1].add(body)

    def enterEnvBegin(self, ctx: _LatexParser.EnvBeginContext):
        env = Environment.from_ctx(ctx, self.parser)
        self.stack.append(env)

    def exitEnvEnd(self, ctx: _LatexParser.EnvEndContext):
        env: Node = self.stack.pop()
        assert isinstance(
            env, Environment), "Expected Environment on top of stack."
        env_end = Environment.from_ctx(ctx, self.parser)
        env.end = env_end.end
        expected_env_name = env.env_name
        actual_env_name = str(ctx.TEXT()).strip()
        if expected_env_name != actual_env_name:
            location_str = env.location.range.start.translate(1, 1).format()
            end_location_str = env_end.location.range.start.translate(
                1, 1).format()
            error = LatexException(
                f'Environment unbalanced:'
                f' Expected {expected_env_name} entered ({location_str}) found {actual_env_name} ({end_location_str})')
            self.parser.syntax_errors.append((env.location, error))
        self.stack[-1].add(env)

    def enterInlineEnv(self, ctx: _LatexParser.InlineEnvContext):
        env = InlineEnvironment.from_ctx(ctx, self.parser)
        env_name_ctx = ctx.INLINE_ENV_NAME()
        env_name_range = (
            env_name_ctx.getSymbol().start,
            env_name_ctx.getSymbol().stop + 1
        )
        token = Token(self.parser, *env_name_range, lexeme=str(env_name_ctx))
        env.add_name(token)
        self.stack.append(env)

    def exitInlineEnv(self, ctx: _LatexParser.InlineEnvContext):
        env = self.stack.pop()
        self.stack[-1].add(env)

    def exitText(self, ctx: _LatexParser.TextContext):
        token = Token.from_ctx(ctx, self.parser, lexeme=ctx.getText())
        self.stack[-1].add(token)

    def enterRarg(self, ctx: _LatexParser.RargContext):
        node = Node.from_ctx(ctx, self.parser)
        self.stack.append(node)

    def exitRarg(self, ctx: _LatexParser.RargContext):
        rarg = self.stack.pop()
        env: Node = self.stack[-1]
        assert isinstance(
            env, Environment), "Expected Environment on top of stack."
        if env.name is None:
            env.add_name(rarg)
        else:
            env.add_rarg(rarg)

    def enterArgument(self, ctx: _LatexParser.ArgumentContext):
        node = OArgument.from_ctx(ctx, self.parser)
        self.stack.append(node)

    def exitArgument(self, ctx: _LatexParser.ArgumentContext):
        node = self.stack.pop()
        assert isinstance(
            node, OArgument), "Expected Optional Argument on top of stack."
        top = self.stack[-1]
        assert isinstance(
            top, Environment), "Expected Environment on top of stack."
        top.add_oarg(node)

    def enterArgumentName(self, ctx: _LatexParser.ArgumentNameContext):
        node = Node.from_ctx(ctx, self.parser)
        self.stack.append(node)

    def exitArgumentName(self, ctx: _LatexParser.ArgumentNameContext):
        name = self.stack.pop()
        oarg = self.stack[-1]
        assert isinstance(
            oarg, OArgument), "Expected Optional Argument on top of stack."
        oarg.add_name(name)

    def enterArgumentValue(self, ctx: _LatexParser.ArgumentValueContext):
        node = Node.from_ctx(ctx, self.parser)
        self.stack.append(node)

    def exitArgumentValue(self, ctx: _LatexParser.ArgumentValueContext):
        value = self.stack.pop()
        oarg = self.stack[-1]
        assert isinstance(
            oarg, OArgument), "Expected OArgument on top of stack."
        oarg.add_value(value)
