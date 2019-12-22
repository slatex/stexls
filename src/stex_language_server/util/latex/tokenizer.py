from __future__ import annotations
import re
from typing import Optional, Callable, Iterable, List, Iterator, Tuple, Union
from stex_language_server.util.latex import parser

__all__ = ['LatexTokenizer', 'LatexToken']

DEFAULT_WORDS = r'''(?:[\w\d_]|(?<!^)\-|\{\\ss\}|\\ss|\\\"(?:a|A|o|O|u|U|s|S))+(?:'s|(?<=n)'t)?|\!|\@|\#|\$|\%|\^|\&|\*|\(|\)|\_|\+|\=|\-|\[|\]|\'|\\|\.|\/|\?|\>|\<|\,|\:|;|\"|\||\{|\}|s+'''

DEFAULT_FILTER = r'''\s+|\@|\#|\^|\*|\_|\+|\=|\[|\]|\\|\/|\>|\<|\{|\}'''

class LatexToken:
    def __init__(self, lexeme: str, begin: int, end: int, envs: tuple):
        self.lexeme = lexeme
        self.begin = begin
        self.end = end
        self.envs = envs
    
    def __iter__(self):
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
        words: str = DEFAULT_WORDS,
        token_filter: str = DEFAULT_FILTER):
        self.math_token = '<math>'
        self._words = re.compile(words)
        self._token_filter = re.compile(token_filter)
        # buffer the tokens of the root
        self._tokens: List[parser.Token] = list(root.tokens)

    def __iter__(self) -> Iterator[LatexToken]:
        for token in self._tokens:
            if token.envs and '$' in token.envs:
                yield LatexToken(
                    self.math_token or token.lexeme,
                    token.begin,
                    token.end,
                    token.envs)
            else:
                for word in self._words.finditer(token.lexeme):
                    if self._token_filter.fullmatch(word.group()):
                        continue
                    begin, end = word.span()
                    yield LatexToken(
                        word.group(),
                        token.begin + begin,
                        token.begin + end,
                        token.envs)

    @staticmethod
    def from_file(file: Union[str, parser.LatexParser], lower: bool = True):
        if not isinstance(file, parser.LatexParser):
            file = parser.LatexParser(file, lower=lower)
        if not file.success:
            return None
        return LatexTokenizer(file.root)

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
