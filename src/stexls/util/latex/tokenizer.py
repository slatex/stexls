''' This is an important module which
takes a parsed latex file using the stex.util.latex.parser.LatexParser
and parses the parse tree into it's more useful tokens, preserving
environment, location and parse tree structure.
'''
from __future__ import annotations
import re
from typing import Optional, Callable, Iterable, List, Iterator, Tuple, Union
from stexls.util.latex import parser

__all__ = ['LatexTokenizer', 'LatexToken']

DEFAULT_WORDS = r'''(?:[\w\d_]|(?<!^)\-|\{\\ss\}|\\ss|\\\"(?:a|A|o|O|u|U|s|S))+(?:'s|(?<=n)'t)?|\!|\@|\#|\$|\%|\^|\&|\*|\(|\)|\_|\+|\=|\-|\[|\]|\'|\\|\.|\/|\?|\>|\<|\,|\:|;|\"|\||\{|\}|s+'''

DEFAULT_FILTER = r'''\s+|\@|\#|\^|\*|\_|\+|\=|\[|\]|\\|\/|\>|\<|\{|\}'''

class LatexToken:
    ''' A lexical token, which inherited the location and environment
        data from it's latex parent token.
    '''
    def __init__(self, lexeme: str, begin: int, end: int, envs: tuple):
        ''' Initializes the token.
        Parameters:
            lexeme: Actual string of the token.
            begin: 0 indexed begin offset in the original file.
            end: 0 indexed end offset in the original file.
            envs: Latex environment information at the token's position.
        '''
        self.lexeme = lexeme
        self.begin = begin
        self.end = end
        self.envs = envs

    def __iter__(self):
        ' Yields the members, imitating a tuple. '
        yield self.lexeme
        yield self.begin
        yield self.end
        yield self.envs

    def __repr__(self) -> str:
        return f'[LatexToken lexeme="{self.lexeme}" begin={self.begin} end={self.end} envs={self.envs}]'


class LatexTokenizer:
    ' Extracts the tokens with their environments from a parsed latex file. '
    def __init__(
        self,
        root: parser.Node,
        lower: bool = True,
        words: str = DEFAULT_WORDS,
        token_filter: str = DEFAULT_FILTER):
        self.lower = lower
        self.math_token = '<math>'
        self._words = re.compile(words)
        self._token_filter = re.compile(token_filter)
        # buffer the tokens of the root
        self._tokens: List[parser.Token] = list(root.tokens)

    def __iter__(self) -> Iterator[LatexToken]:
        ' Parses the lexical tokens in the file and yields them. '
        for token in self._tokens:
            if token.envs and '$' in token.envs:
                lexeme = self.math_token or token.lexeme
                if self.lower:
                    lexeme = lexeme.lower()
                yield LatexToken(
                    lexeme,
                    token.begin,
                    token.end,
                    token.envs)
            else:
                for word in self._words.finditer(token.lexeme):
                    if self._token_filter.fullmatch(word.group()):
                        continue
                    begin, end = word.span()
                    lexeme = word.group()
                    if self.lower:
                        lexeme = lexeme.lower()
                    yield LatexToken(
                        lexeme,
                        token.begin + begin,
                        token.begin + end,
                        token.envs)

    @staticmethod
    def from_file(file: Union[str, parser.LatexParser], lower: bool = True) -> LatexTokenizer:
        ' Creates this tokenizer directly from a file, parsing it beforehand. '
        if not isinstance(file, parser.LatexParser):
            file = parser.LatexParser(file)
        if not file.success:
            return None
        return LatexTokenizer(file.root, lower=lower)

def _replace_german_characters(text: str) -> str:
    return (text.
            replace('\\ss', 'ß').
            replace('\\"s', 'ß').
            replace('\\"a', 'ä').
            replace('\\"A', 'ä').
            replace('\\"u', 'ü').
            replace('\\"U', 'Ü').
            replace('\\"o', 'ö').
            replace('\\"O', 'Ö'))
