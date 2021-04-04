''' This is an important module which
takes a parsed latex file using the stex.util.latex.parser.LatexParser
and parses the parse tree into it's more useful tokens, preserving
environment, location and parse tree structure.
'''
from __future__ import annotations
from pathlib import Path

import re
from typing import Iterator, List, Optional, Tuple, Union

from stexls.util.latex import parser
from stexls.vscode import Range

__all__ = ['LatexTokenizer', 'LatexToken']

# TODO: Redo the word regex
DEFAULT_WORDS = (
    r'''(?:[\w\d_]|(?<!^)\-|\{\\ss\}|\\ss|\\\"(?:a|A|o|O|u|U|s|S))+'''
    r'''(?:'s|(?<=n)'t)?|\!|\@|\#|\$|\%|\^|\&|\*|\(|\)|\_|\+|\=|\-|\[|\]|\'|\\|\.|\/|\?|\>|\<|\,|\:|;|\"|\||\{|\}|s+'''
)

DEFAULT_FILTER = r'''\s+|\@|\#|\^|\*|\_|\+|\=|\[|\]|\\|\/|\>|\<|\{|\}'''


class LatexToken:
    ''' A lexical token, which inherited the location and environment
        data from it's latex parent token.

        Why does this exists?
        Because the Token defined in util.latex contains a reference to the parser which is not needed anymore.
    '''

    def __init__(self, range: Range, lexeme: str, envs: Tuple[str, ...]):
        ''' Initializes the token.
        Parameters:
            lexeme: Actual string of the token.
            envs: Latex environment information at the token's position.
        '''
        self.range = range
        self.lexeme = lexeme
        self.envs = envs

    def __repr__(self) -> str:
        return f'[LatexToken "{self.lexeme}" at {self.range.start.format()} envs={self.envs}]'


class LatexTokenizer:
    ''' Extracts the tokens with their environments from a parsed latex file. '''

    def __init__(
            self,
            root: parser.Node,
            lower: bool = True,
            math_token: Optional[str] = '<math>',
            words: str = DEFAULT_WORDS,
            token_filter: str = DEFAULT_FILTER):
        self.lower = lower
        self.math_token = math_token
        self._words = re.compile(words)
        self._token_filter = re.compile(token_filter)
        # buffer the tokens of the root
        self._tokens: List[parser.Token] = list(root.tokens)

    def tokens(self) -> Iterator[LatexToken]:
        ' Parses the lexical tokens in the file and yields them. '
        for token in self._tokens:
            if token.envs and '$' in token.envs:
                lexeme = self.math_token or token.lexeme
                if self.lower:
                    lexeme = lexeme.lower()
                yield LatexToken(
                    token.range,
                    lexeme,
                    token.envs)
            else:
                for word in self._words.finditer(token.lexeme):
                    if self._token_filter.fullmatch(word.group()):
                        continue
                    begin, end = word.span()
                    lexeme = word.group()
                    if self.lower:
                        lexeme = lexeme.lower()
                    offsetted_token = parser.Token(
                        token.parser,
                        token.begin + begin,
                        token.begin + end,
                        lexeme)
                    yield LatexToken(
                        offsetted_token.range,
                        lexeme,
                        token.envs)

    @staticmethod
    def from_file(file: Union[str, Path, parser.LatexParser], lower: bool = True) -> Optional[LatexTokenizer]:
        ' Creates this tokenizer directly from a file, parsing it beforehand. '
        if isinstance(file, parser.LatexParser):
            latex_parser = file
        else:
            latex_parser = parser.LatexParser(file)
        if not latex_parser.parsed:
            latex_parser.parse()
        if latex_parser.root is None:
            return None
        return LatexTokenizer(latex_parser.root, lower=lower)


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
