from __future__ import annotations
import itertools, os, re, copy, antlr4
from typing import Iterator, Pattern, List, Optional, Tuple
from antlr4.error.ErrorListener import ErrorListener

from stexls.util.latex.grammar.out.LatexLexer import LatexLexer as _LatexLexer
from stexls.util.latex.grammar.out.LatexParserListener import LatexParserListener as _LatexParserListener
from stexls.util.latex.grammar.out.LatexParser import LatexParser as _LatexParser


__all__ = ['LatexParser', 'InlineEnvironment', 'Environment', 'Token', 'MathToken', 'Node']


class Node:
    ' Base class for the syntax tree content. '
    def __init__(self, begin: int, end: int):
        """ Creates a node.
        Parameters:
            begin: Zero indexed begin offset in the source file.
            end: Zero indexed end offset in the source file.
        """
        assert isinstance(end, int)
        assert isinstance(begin, int)
        self.begin = begin
        self.end = end
        self.children = []
        self.parent = None

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
        ' Lists all environments of all nodes recursively. '
        env = (self.env_name,) if self.env_name else ()
        if not self.parent:
            return env
        return self.parent.envs + env

    @property
    def env_name(self):
        ' The environment name of this node. None if this node is not an environment. '
        return None

    def finditer(self, env_pattern: Pattern) -> Iterator[Node]:
        ' Iterator with only the nodes that match the given pattern. '
        for child in self.children:
            yield from child.finditer(env_pattern)


class Token(Node):
    ' A token is a leaf node that contains the actual text of the source file. '
    def __init__(self, begin: int, end: int, lexeme: str):
        ''' Constructs a token with text and position information.
        Parameters:
            begin: Zero indexed begin offset of the text.
            end: Zero indexed end offset of the text.
            lexeme: The actual text in the source document.
        '''
        super().__init__(begin, end)
        self.lexeme = lexeme

    @property
    def tokens(self):
        yield self

    def add(self, child):
        ' Tokens can not have children. '
        raise RuntimeError("Tokens can not add children.")

    def __repr__(self):
        return self.lexeme


class MathToken(Token):
    ' A special token that represents an environment that contains math. '
    @property
    def env_name(self):
        return '$'


class Environment(Node):
    ''' An environment is a node of the form
        \\begin{name}[<oargs>]{<rargs>}
            <text>
        \\end{name}
        The oargs and rargs do not contain text.
    '''
    def __init__(self, begin: int, end: int):
        ''' Initializes an environment node with an empty rarg and oarg array.
        Parameters:
            begin: Zero indexed begin offset of where the environment's first character is (the first "\\")
            end: Zero indexed end offset of where the environment's last character is (usually a "}")
        '''
        super().__init__(begin, end)
        self.name = None
        self.rargs = []
        self.oargs = []

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
        assert isinstance(name_token, Token)
        if self.name is not None:
            raise ValueError('Environment already has a name provider token.')
        if name_token.parent is not None:
            raise ValueError('Environment name provider token already has a parent.')
        self.name = name_token
        name_token.parent = self

    @property
    def env_name(self) -> str:
        ''' Gets the environment's name from the provided name token,
            raises if no token provided.
        '''
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


class LatexParser(_LatexParserListener):
    ''' Implements the antlr4 methods for parsing a latex file.
        Various information about the parsed file is also stored.
        Most importantly the root member, which contains the document root
        node, from which all other tokens and environments can be queried.
        Success and error information as well as position and offset
        transformation data is also stored.
    '''
    def enterMain(self, ctx: _LatexParser.MainContext):
        self._stack.append(Node(ctx.start.start, ctx.stop.stop + 1))

    def exitMain(self, ctx: _LatexParser.MainContext):
        assert len(self._stack) == 1

    def enterInlineEnv(self, ctx: _LatexParser.InlineEnvContext):
        env = InlineEnvironment(ctx.start.start, ctx.stop.stop + 1)
        symbol = ctx.INLINE_ENV_NAME().getSymbol()
        env.add_name(Token(symbol.start + 1, symbol.stop + 1, str(ctx.INLINE_ENV_NAME())[1:]))
        self._stack.append(env)

    def exitInlineEnv(self, ctx: _LatexParser.InlineEnvContext):
        env = self._stack.pop()
        self._stack[-1].add(env)

    def enterEnv(self, ctx: _LatexParser.EnvContext):
        self._stack.append(Environment(ctx.start.start, ctx.stop.stop + 1))

    def exitEnv(self, ctx: _LatexParser.EnvContext):
        env = self._stack.pop()
        self._stack[-1].add(env)

    def enterEnvBegin(self, ctx: _LatexParser.EnvBeginContext):
        pass

    def exitEnvBegin(self, ctx: _LatexParser.EnvBeginContext):
        assert isinstance(self._stack[-1], Environment)
        symbol = ctx.TOKEN().getSymbol()
        self._stack[-1].add_name(Token(symbol.start, symbol.stop + 1, str(ctx.TOKEN())))

    def enterEnvEnd(self, ctx: _LatexParser.EnvEndContext):
        pass

    def exitEnvEnd(self, ctx: _LatexParser.EnvEndContext):
        assert isinstance(self._stack[-1], Environment)
        if not self._stack[-1].name.lexeme.strip() == str(ctx.TOKEN()).strip():
            raise Exception(f"In file '{self.file}', environment unbalanced:"
                            f" Expected {self._stack[-1].name.lexeme.strip()} found {str(ctx.TOKEN()).strip()}")

    def enterMath(self, ctx: _LatexParser.MathContext):
        pass

    def exitMath(self, ctx: _LatexParser.MathContext):
        symbol = ctx.MATH_ENV().getSymbol()
        self._stack[-1].add(MathToken(symbol.start, symbol.stop + 1, str(ctx.MATH_ENV())))

    def enterToken(self, ctx: _LatexParser.TokenContext):
        pass

    def exitToken(self, ctx: _LatexParser.TokenContext):
        symbol = ctx.TOKEN().getSymbol()
        self._stack[-1].add(Token(symbol.start, symbol.stop + 1, str(ctx.TOKEN())))

    def enterOarg(self, ctx: _LatexParser.OargContext):
        self._stack.append(Node(ctx.start.start, ctx.stop.stop + 1))

    def exitOarg(self, ctx: _LatexParser.OargContext):
        oarg = self._stack.pop()
        assert isinstance(self._stack[-1], Environment)
        self._stack[-1].add_oarg(oarg)

    def enterRarg(self, ctx: _LatexParser.RargContext):
        self._stack.append(Node(ctx.start.start, ctx.stop.stop + 1))

    def exitRarg(self, ctx: _LatexParser.RargContext):
        rarg = self._stack.pop()
        assert isinstance(self._stack[-1], Environment)
        self._stack[-1].add_rarg(rarg)

    def offset_to_position(self, offset: int) -> Tuple[int, int]:
        """ Returns the position (line, column) of the offset
            where line, column start at the 0th line and character.
        """
        for i, len in enumerate(self._line_lengths):
            if offset < len:
                break
            offset -= len
        return i, offset

    def position_to_offset(self, line: int, character: int) -> int:
        ' Translate zero indexed line and character into corresponding offset. '
        return sum(self._line_lengths[:line]) + character

    def get_text_by_offset(self, begin: int, end: int) -> str:
        ' Returns the text between zero indexed begin and end offsets. '
        return self.source[begin:end]
    
    def __init__(self, file_or_document: str, lower: bool = False, ignore_exceptions: bool = False):
        ''' Creates a parser and parses the file.
            Initializes also the following members:
                file: Path to the file that was parsed, None if the file_or_document argument was not a file.
                success: Parsing succes status flag.
                source: The actual text of the loaded file or equal to file_or_document, if not a file.
                exception: Stored exception if ignore_exceptions was set.
                root: Node of the document's parse tree.
                syntax_errors: List of all syntax erros which occured during parsing.
        Parameters:
            file_or_document: A which is either a path to a latex file or the file's content itself.
            lower: Enables calling lower() on the file source text.
            ignore_exceptions:
                If enabled, exceptions thrown during parsing
                will be stored in self.exceptions instead of raising.
        '''
        self.file: Optional[str] = None
        self.success: bool = False
        self._stack = []
        self.source: str = None
        self.exception: Optional[Exception] = None
        self.root: Optional[Node] = None
        self.syntax_errors: List[SyntaxErrorInformation] = None
        try:
            if file_or_document is None:
                raise ValueError('file_or_document must not be None')
            if os.path.isfile(file_or_document):
                self.file = file_or_document
                with open(self.file, encoding='utf-8') as ref:
                    self.source = ref.read()
            else:
                self.source = file_or_document
            if lower:
                self.source = self.source.lower()
            self._line_lengths = [len(line)+1 for line in self.source.split('\n')]
            lexer = _LatexLexer(antlr4.InputStream(self.source))
            stream = antlr4.CommonTokenStream(lexer)
            parser = _LatexParser(stream)
            error_listener = _SyntaxErrorErrorListener(self.file)
            parser.addErrorListener(error_listener)
            tree = parser.main()
            walker = antlr4.ParseTreeWalker()
            walker.walk(self, tree)
            self.root = self._stack[0]
            self.syntax_errors = error_listener.syntax_errors
            self.success = True
        except Exception as e:
            if ignore_exceptions:
                self.exception = e
            else:
                raise
        finally:
            del self._stack


class SyntaxErrorInformation:
    ' Contains information about a syntax error that occured during parsing. '
    def __init__(self, file: Optional[str], line: int, character: int, message: str):
        ''' Initialize syntax error information container.
        Parameters:
            file: Optional path to a file.
            line: The zero indexed line the error occured on.
            character: The zero indexed character the error occured on.
            message: Error information message.
        '''
        self.file = file
        self.line = line
        self.character = character
        self.message = message


class _SyntaxErrorErrorListener(ErrorListener):
    ' Error listener that captures syntax errors during parsing. '
    def __init__(self, file: str):
        super().__init__()
        self.file = file
        self.syntax_errors: List[SyntaxErrorInformation] = []

    def syntaxError(self, recognizer, offendingSymbol, line, column, msg, e):
        self.syntax_errors.append(SyntaxErrorInformation(self.file, line, column, msg))
