from __future__ import annotations
import itertools, os, re, copy, antlr4
from typing import Iterator, Pattern, List, Optional, Tuple, Callable
import tempfile

from antlr4.error.ErrorListener import ErrorListener

from stexls.util.latex.grammar.out.LatexLexer import LatexLexer as _LatexLexer
from stexls.util.latex.grammar.out.LatexParserListener import LatexParserListener as _LatexParserListener
from stexls.util.latex.grammar.out.LatexParser import LatexParser as _LatexParser


__all__ = ['LatexParser', 'InlineEnvironment', 'Environment', 'Token', 'MathToken', 'Node']


class Node:
    ' Base class for the syntax tree content. '
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
        self.parent: Node = None

    @property
    def text(self) -> str:
        " The text this node contains. "
        return self.parser.get_text_by_offset(self.begin, self.end)

    @property
    def text_inside(self) -> str:
        " Get text spanned by first and last child nodes. "
        tokens = list(self.tokens)
        if not tokens:
            start = self.begin
            stop = self.end
        else:
            start = tokens[0].begin
            stop = tokens[-1].end
        return self.parser.get_text_by_offset(start, stop)

    def add(self, node: Node):
        ' Adds a child. '
        if node.parent is not None:
            raise ValueError('Child parent already set.')
        self.children.append(node)
        node.parent = self

    @property
    def tokens(self) -> Iterator[Token]:
        ' Iterator that iterates through all tokens of all children recursively. '
        for child in self.children:
            yield from child.tokens

    @property
    def envs(self) -> List[Environment]:
        ' Recursively determines all environments this node is contained in. '
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
        """ Initializes an environment node with an empty rarg and oarg array.
        Parameters:
            begin: Zero indexed begin offset of where the environment's first character is (the first "\\")
            end: Zero indexed end offset of where the environment's last character is (usually a "}")
        """
        super().__init__(parser, begin, end)
        self.name = None
        self.rargs: List[Node] = []
        self.oargs: List[Node] = []

    def add_oarg(self, oarg: Node):
        ' Register an OArg. '
        if oarg.parent is not None:
            raise ValueError("OArg can't be added to environment: OArg already has a parent.")
        self.oargs.append(oarg)
        oarg.parent = self

    def add_rarg(self, rarg: Node):
        ' Registers an RArg. '
        if rarg.parent is not None:
            raise ValueError("RArg can't be added to environment: RArg already has a parent.")
        self.rargs.append(rarg)
        rarg.parent = self

    def add_name(self, name_token: Token):
        ' Adds a token as a name provider. '
        if self.name is not None:
            raise ValueError('Environment already has a name provider token.')
        if name_token.parent is not None:
            raise ValueError('Environment name provider token already has a parent.')
        self.name = name_token
        name_token.parent = self

    @property
    def env_name(self) -> str:
        """ Gets the environment's name from the provided name token,
            raises if no token provided.
        """
        if self.name is None:
            raise RuntimeError(
                'Unable to get environment name,'
                'because no name token was provided.')
        return self.name.lexeme.strip()

    def finditer(self, env_pattern: Pattern) -> Iterator[Node]:
        if re.fullmatch(env_pattern, self.name.lexeme):
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
    """
    @property
    def tokens(self):
        for arg in self.rargs:
            yield from arg.tokens
        yield from super().tokens


class LatexParser:
    def __init__(self, file: str, encoding: str = 'utf-8'):
        """ Reads and parses the given file using latex syntax.

        Loads the given file and stores the text in self.source.
        The text is parsed and the result is stored in self.root.
        Syntax errors which occured during parsing are also
        retrievable using self.syntax_errors.

        Args:
            file (str): Path to a file.
            encoding (str): Encoding of the file. Defaults to 'utf-8'.
        """
        self.file: str = file
        self.root: Optional[Node] = None
        self.syntax_errors: List[SyntaxErrorInformation] = None
        with open(file, encoding=encoding) as fd:
            self.source: str = fd.read()
        self._line_lengths = [
            len(line) + 1
            for line
            in self.source.split('\n')
        ]
        input_stream = antlr4.InputStream(self.source)
        lexer = _LatexLexer(input_stream)
        stream = antlr4.CommonTokenStream(lexer)
        parser = _LatexParser(stream)
        error_listener = _SyntaxErrorErrorListener(self.file)
        parser.addErrorListener(error_listener)
        listener = _LatexParserListener(self)
        walker = antlr4.ParseTreeWalker()
        parse_tree = parser.main()
        walker.walk(listener, parse_tree)
        self.root = listener.stack[0]
        self.syntax_errors = error_listener.syntax_errors

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
        return LatexParser(file=fd.name, encoding='utf-8')

    def offset_to_position(self, offset: int) -> Tuple[int, int]:
        """ Converts offset to tuple of line and character.

        Args:
            offset (int): 0-indexed offset character in the file.

        Returns:
            Tuple[int, int]: First is the 1-indexed line,
                Second is the 1-indexed character of that line.
        """
        for i, len in enumerate(self._line_lengths):
            if offset < len:
                break
            offset -= len
        return i, offset

    def position_to_offset(self, line: int, character: int) -> int:
        """ Converts 1-indexed line and 1-indexed character to an offset.

        Args:
            line (int): 1-indexed line.
            character (int): 1-indexed character of that line.

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
            else:
                stack.extend(current.children)


class SyntaxErrorInformation:
    ' Contains information about a syntax error that occured during parsing. '
    def __init__(self, file: str, line: int, character: int, message: str):
        """ Initialize syntax error information container.

        Args:
            file (str): Path to file which is referenced by line and character.
            line (int): The zero indexed line the error occured on.
            character (int): The zero indexed character the error occured on.
            message (str): Error information message.
        """
        self.file = file
        self.line = line
        self.character = character
        self.message = message


class _SyntaxErrorErrorListener(ErrorListener):
    ' Error listener that captures syntax errors during parsing. '
    def __init__(self, file: str):
        """ Initializes the error listener with the filename which is to be parsed.

        Args:
            file (str): Filename
        """
        super().__init__()
        self.file = file
        self.syntax_errors: List[SyntaxErrorInformation] = []

    def syntaxError(self, recognizer, offendingSymbol, line, column, msg, e):
        info = SyntaxErrorInformation(self.file, line, column, msg)
        self.syntax_errors.append(info)


class _LatexParserListener(_LatexParserListener):
    ' Implements the antlr4 methods for parsing a latex file. '
    def __init__(self, parser: LatexParser):
        super().__init__()
        self.parser = parser
        self.stack: List[Node] = []

    @staticmethod
    def _get_ctx_range(ctx):
        return ctx.start.start, ctx.stop.stop + 1

    def enterMain(self, ctx: _LatexParser.MainContext):
        range = _LatexParserListener._get_ctx_range(ctx)
        node = Node(self.parser, *range)
        self.stack.append(node)

    def exitMain(self, ctx: _LatexParser.MainContext):
        assert len(self.stack) == 1, "Broken parser stack."

    def enterInlineEnv(self, ctx: _LatexParser.InlineEnvContext):
        range = _LatexParserListener._get_ctx_range(ctx)
        env = InlineEnvironment(self.parser, *range)
        env_name_ctx = ctx.INLINE_ENV_NAME()
        env_name = str(env_name_ctx)[1:]
        env_name_range = (env_name_ctx.getSymbol().start, env_name_ctx.getSymbol().stop)
        token = Token(self.parser, *env_name_range, env_name)
        env.add_name(token)
        self.stack.append(env)

    def exitInlineEnv(self, ctx: _LatexParser.InlineEnvContext):
        env = self.stack.pop()
        self.stack[-1].add(env)

    def enterEnv(self, ctx: _LatexParser.EnvContext):
        range = _LatexParserListener._get_ctx_range(ctx)
        env = Environment(self.parser, *range)
        self.stack.append(env)

    def exitEnv(self, ctx: _LatexParser.EnvContext):
        env = self.stack.pop()
        self.stack[-1].add(env)

    def exitEnvBegin(self, ctx: _LatexParser.EnvBeginContext):
        assert isinstance(self.stack[-1], Environment), "Broken parser stack."
        lexeme = str(ctx.TOKEN())
        range = _LatexParserListener._get_ctx_range(ctx)
        token = Token(self.parser, *range, lexeme)
        self.stack[-1].add_name(token)

    def exitEnvEnd(self, ctx: _LatexParser.EnvEndContext):
        assert isinstance(self.stack[-1], Environment), "Broken parser stack."
        expected_env_name = self.stack[-1].name.lexeme.strip()
        actual_env_name = str(ctx.TOKEN()).strip()
        if expected_env_name != actual_env_name:
            raise RuntimeError(f"Environment unbalanced:"
                               f" Expected {expected_env_name} found {actual_env_name}")

    def exitMath(self, ctx: _LatexParser.MathContext):
        lexeme = str(ctx.MATH_ENV())
        range = _LatexParserListener._get_ctx_range(ctx)
        math = MathToken(self.parser, *range, lexeme)
        self.stack[-1].add(math)

    def exitToken(self, ctx: _LatexParser.TokenContext):
        token_ctx = ctx.TOKEN()
        lexeme = str(token_ctx)
        range = _LatexParserListener._get_ctx_range(ctx)
        token = Token(self.parser, *range, lexeme)
        self.stack[-1].add(token)

    def enterOarg(self, ctx: _LatexParser.OargContext):
        range = _LatexParserListener._get_ctx_range(ctx)
        node = Node(self.parser, *range)
        self.stack.append(node)

    def exitOarg(self, ctx: _LatexParser.OargContext):
        oarg = self.stack.pop()
        assert isinstance(self.stack[-1], Environment), "Broken parser stack."
        self.stack[-1].add_oarg(oarg)

    def enterRarg(self, ctx: _LatexParser.RargContext):
        range = _LatexParserListener._get_ctx_range(ctx)
        node = Node(self.parser, *range)
        self.stack.append(node)

    def exitRarg(self, ctx: _LatexParser.RargContext):
        rarg = self.stack.pop()
        assert isinstance(self.stack[-1], Environment), "Broken parser stack."
        self.stack[-1].add_rarg(rarg)
