from __future__ import annotations
from typing import Tuple, List, Iterator, Union, Pattern
import itertools

import os
import re

from .grammar.out.SmglomLatexLexer import SmglomLatexLexer
from .grammar.out.SmglomLatexParserListener import SmglomLatexParserListener
from .grammar.out.SmglomLatexParser import SmglomLatexParser
import antlr4

__all__ = ['LatexParser', 'InlineEnvironment', 'Environment', 'Token', 'Math', 'Node']


class Node:
    def __init__(self, begin: int, end: int, parser: LatexParser):
        """
        Creates a node.
        :param begin: Begin offset, where the next character is the first character.
        :param end: End exclusive offset. The pointed to character is not included.
        :param parser: Parser that created this node.
        """
        self.begin = begin
        self.end = end
        assert isinstance(end, int)
        assert isinstance(begin, int)
        self.children = []
        self.parent = None
        self.parser = parser
        assert isinstance(parser, LatexParser)

    def remove_brackets(self):
        """ Removes the first and the last character from the tracked range by moving the begin and end offsets.
        Throws if []{}()<> are not found.
        :returns self
        """
        if (self.parser.source[self.begin] not in ('(', '[', '{', '<') or
                self.parser.source[self.end-1] not in (')', ']', '}', '>')):
            raise RuntimeError('Expected node text to begin and end with brackets (\"()[]{}<>\"),'
                               f'but found "{self.parser.source[self.begin]}" and "{self.parser.source[self.end-1]}"')
        self.begin += 1
        self.end -= 1
        return self

    def split_range(self,
                    pattern: Pattern,
                    keep_delimeter: bool = False,
                    as_position: bool = False,
                    return_lexemes: bool = False) -> Union[Iterator[Tuple[int, int]],
                                                           Iterator[Tuple[int, int, str]],
                                                           Iterator[Tuple[Tuple[int, int], Tuple[int, int]]],
                                                           Iterator[Tuple[Tuple[int, int], Tuple[int, int], str]]]:
        """ Splits the text of this node using a pattern and returns the (begin, end) offsets of each split. """
        parts = re.split(pattern, self.text)
        delimeters = re.finditer(pattern, self.text)
        begin = self.begin
        for part, match in itertools.zip_longest(parts, delimeters):
            if as_position:
                yield ((self.parser.offset_to_position(begin),
                        self.parser.offset_to_position(begin + len(part)))
                       + ((part,) if return_lexemes else ()))
            else:
                yield (begin, begin + len(part)) + ((part,) if return_lexemes else ())
            if match is not None:
                begin += len(part)
                match_string = match.group(0)
                if keep_delimeter:
                    if as_position:
                        yield ((self.parser.offset_to_position(begin),
                               self.parser.offset_to_position(begin + len(match_string)))
                               + ((match_string,) if return_lexemes else ()))
                    else:
                        yield (begin, begin + len(match_string)) + ((match_string,) if return_lexemes else ())
                begin += len(match_string)

    @property
    def text(self) -> str:
        """ :returns Text between begin and end offsets. """
        return self.parser.source[self.begin:self.end]

    @property
    def begin_position(self) -> Tuple[int, int]:
        """ :returns The (line, column) position of the begin. """
        return self.parser.offset_to_position(self.begin)

    @property
    def end_position(self) -> Tuple[int, int]:
        """ :returns The (line, column) position of the end. """
        return self.parser.offset_to_position(self.end)

    @property
    def full_range(self) -> Tuple[Tuple[int, int], Tuple[int, int]]:
        """ Returns A tuple of two (line, column) begin and end positions. """
        return self.begin_position, self.end_position

    @property
    def effective_range(self) -> Tuple[Tuple[int, int], Tuple[int, int]]:
        """ Returns the range of the text without whitespaces to the left and the right. """
        text = self.text
        ws_count_left = len(text) - len(text.lstrip())
        ws_count_right = len(text) - len(text.rstrip())
        return (self.parser.offset_to_position(self.begin + ws_count_left),
                self.parser.offset_to_position(self.end - ws_count_right))

    def add(self, node):
        """ Adds a child to this node. """
        self.children.append(node)
        node.parent = self

    @property
    def tokens(self) -> Iterator[Token]:
        """ :returns Iterator of all tokens inside this node and children. """
        for child in self.children:
            yield from child.tokens

    @property
    def envs(self) -> List[Environment]:
        """ :returns List of the environments this node has as parents including itself. """
        env = [self.env_name] if self.env_name else []
        if not self.parent:
            return env
        return self.parent.envs + env

    @property
    def env_name(self):
        """ :returns The environment name of this node. None if this node is not an environment. """
        return None

    def finditer(self, env_pattern: Pattern) -> Iterator[Node]:
        """ :returns Iterator with all environment nodes whose env_name matches the given regex pattern. """
        for child in self.children:
            yield from child.finditer(env_pattern)


class Token(Node):
    """ A token is anything that is not needed to build the latex environment structure. """
    def __init__(self, lexeme: str, begin: int, end: int, parser: LatexParser):
        super().__init__(begin, end, parser)
        assert isinstance(lexeme, str)
        self.lexeme = lexeme
        ws_count_left = len(self.lexeme) - len(self.lexeme.lstrip())
        ws_count_right = len(self.lexeme) - len(self.lexeme.rstrip())
        self._effective_range = (
            self.parser.offset_to_position(self.begin + ws_count_left),
            self.parser.offset_to_position(self.end - ws_count_right))

    @property
    def effective_range(self) -> Tuple[Tuple[int, int], Tuple[int, int]]:
        """ Returns the range of the token without whitespaces to the left and the right. """
        return self._effective_range

    @property
    def tokens(self):
        return [self]

    def add(self, child):
        """ Tokens can't have children. """
        raise RuntimeError("Tokens can not add children.")

    def __repr__(self):
        return self.lexeme


class Math(Token):
    @property
    def env_name(self):
        return '$'


class Environment(Node):
    def __init__(self, begin: int, end: int, parser: LatexParser):
        super().__init__(begin, end, parser)
        self.name = None
        self.rargs = []
        self.oargs = []

    def add_oarg(self, oarg: Node):
        """ Adds a node as a oarg. """
        self.oargs.append(oarg)
        oarg.parent = self

    def add_rarg(self, rarg: Node):
        """ Adds a node as a rarg. """
        self.rargs.append(rarg)
        rarg.parent = self

    def add_name(self, name_token: Token):
        """ Adds a token as name provider. """
        assert isinstance(name_token, Token)
        self.name = name_token
        name_token.parent = self

    @property
    def env_name(self) -> str:
        return self.name.text.strip()

    def finditer(self, env_pattern):
        if re.fullmatch(env_pattern, self.name.lexeme):
            yield self
        else:
            yield from super().finditer(env_pattern)


class InlineEnvironment(Environment):
    @property
    def tokens(self):
        for arg in self.rargs:
            yield from arg.tokens
        yield from super().tokens


class LatexParser(SmglomLatexParserListener):
    def enterMain(self, ctx: SmglomLatexParser.MainContext):
        self._stack.append(Node(ctx.start.start, ctx.stop.stop + 1, self))

    def exitMain(self, ctx: SmglomLatexParser.MainContext):
        assert len(self._stack) == 1

    def enterInlineEnv(self, ctx: SmglomLatexParser.InlineEnvContext):
        env = InlineEnvironment(ctx.start.start, ctx.stop.stop + 1, self)
        symbol = ctx.INLINE_ENV_NAME().getSymbol()
        env.add_name(Token(str(ctx.INLINE_ENV_NAME())[1:], symbol.start + 1, symbol.stop + 1, self))
        self._stack.append(env)

    def exitInlineEnv(self, ctx: SmglomLatexParser.InlineEnvContext):
        env = self._stack.pop()
        self._stack[-1].add(env)

    def enterEnv(self, ctx: SmglomLatexParser.EnvContext):
        self._stack.append(Environment(ctx.start.start, ctx.stop.stop + 1, self))

    def exitEnv(self, ctx: SmglomLatexParser.EnvContext):
        env = self._stack.pop()
        self._stack[-1].add(env)

    def enterEnvBegin(self, ctx: SmglomLatexParser.EnvBeginContext):
        pass

    def exitEnvBegin(self, ctx: SmglomLatexParser.EnvBeginContext):
        assert isinstance(self._stack[-1], Environment)
        symbol = ctx.TOKEN().getSymbol()
        self._stack[-1].add_name(Token(str(ctx.TOKEN()), symbol.start, symbol.stop + 1, self))

    def enterEnvEnd(self, ctx: SmglomLatexParser.EnvEndContext):
        pass

    def exitEnvEnd(self, ctx: SmglomLatexParser.EnvEndContext):
        assert isinstance(self._stack[-1], Environment)
        if not self._stack[-1].name.text.strip() == str(ctx.TOKEN()).strip():
            raise Exception(f"Environment unbalanced: Expected {self._stack[-1].name.text.strip()} found {str(ctx.TOKEN()).strip()}")

    def enterMath(self, ctx: SmglomLatexParser.MathContext):
        pass

    def exitMath(self, ctx: SmglomLatexParser.MathContext):
        symbol = ctx.MATH_ENV().getSymbol()
        self._stack[-1].add(Math(str(ctx.MATH_ENV()), symbol.start, symbol.stop + 1, self))

    def enterToken(self, ctx: SmglomLatexParser.TokenContext):
        pass

    def exitToken(self, ctx: SmglomLatexParser.TokenContext):
        symbol = ctx.TOKEN().getSymbol()
        self._stack[-1].add(Token(str(ctx.TOKEN()), symbol.start, symbol.stop + 1, self))

    def enterOarg(self, ctx: SmglomLatexParser.OargContext):
        self._stack.append(Node(ctx.start.start, ctx.stop.stop + 1, self))

    def exitOarg(self, ctx: SmglomLatexParser.OargContext):
        oarg = self._stack.pop()
        assert isinstance(self._stack[-1], Environment)
        self._stack[-1].add_oarg(oarg)

    def enterRarg(self, ctx: SmglomLatexParser.RargContext):
        self._stack.append(Node(ctx.start.start, ctx.stop.stop + 1, self))

    def exitRarg(self, ctx: SmglomLatexParser.RargContext):
        rarg = self._stack.pop()
        assert isinstance(self._stack[-1], Environment)
        self._stack[-1].add_rarg(rarg)

    def offset_to_position(self, offset: int) -> Tuple[int, int]:
        """ Returns the position (line, column) of the offset
            where line, column start at the 0th line and character.
        """
        for i, len in enumerate(self._line_lengths):
            if offset < len:
                return i + 1, offset + 1
            offset -= len

    def position_to_offset(self, line: int, column: int) -> int:
        """ Transforms a given 1-indexed line and column into the corresponding offset for the registered file. """
        return sum(self._line_lengths[:line - 1]) + column - 1

    def get_text_by_offset(self, begin: int, end: int) -> str:
        """ Gets the text between the two begin and end offsets. (exclusive end) """
        return self.source[begin:end]

    def get_text(self, begin: Tuple[int, int], end: Tuple[int, int]) -> str:
        """ Gets the text between the two range begin and end markes. (exclusive end) """
        return self.source[self.position_to_offset(*begin):self.position_to_offset(*end)]

    def __init__(self, file_or_document: str, ignore_exceptions: bool = True):
        """
        Creates a parser and parses the file.

        :param file_or_document: A string either which is either a path to a latex file or is a latex string.
        :param ignore_exceptions: If set to True then exceptions are ignored and saved in self.exception if one occured.
                                    Furthermore is the self.success flag set to false if an exception occured.
        """
        self.file = None
        self.success = False
        self._stack = []
        self.source = None
        self.exception = None
        try:
            if os.path.isfile(file_or_document):
                self.file = file_or_document
                with open(self.file, encoding='utf-8') as ref:
                    self.source = ref.read()
            else:
                self.source = file_or_document
            self._line_lengths = [len(line)+1 for line in self.source.split('\n')]
            lexer = SmglomLatexLexer(antlr4.InputStream(self.source))
            stream = antlr4.CommonTokenStream(lexer)
            parser = SmglomLatexParser(stream)
            parser._errHandler = antlr4.BailErrorStrategy()
            tree = parser.main()
            walker = antlr4.ParseTreeWalker()
            walker.walk(self, tree)
            self.root = self._stack[0]
            self.success = True
        except Exception as e:
            if ignore_exceptions:
                self.exception = str(e)
            else:
                raise
        finally:
            del self._stack
