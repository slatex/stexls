from __future__ import annotations
import re
from typing import Optional, Callable, Iterable, List, Iterator, Tuple, Union
from stex_language_server.util.latex.parser import LatexParser, Token, Node

DEFAULT_WORDS = r'''(?:[\w\d_]|(?<!^)\-|\{\\ss\}|\\ss|\\\"(?:a|A|o|O|u|U|s|S))+(?:'s|(?<=n)'t)?|\!|\@|\#|\$|\%|\^|\&|\*|\(|\)|\_|\+|\=|\-|\[|\]|\'|\\|\.|\/|\?|\>|\<|\,|\:|;|\"|\||\{|\}|s+'''

DEFAULT_FILTER = r'''\s+|\@|\#|\^|\*|\_|\+|\=|\[|\]|\\|\/|\>|\<|\{|\}'''

class LatexTokenStream:
    ' Creates a stream of text tokens in a latex file including position and environment information. '
    def __init__(
        self,
        root: Node,
        words: str = DEFAULT_WORDS,
        token_filter: str = DEFAULT_FILTER):
        self.words = re.compile(words)
        self.token_filter = re.compile(token_filter)
        # buffer the tokens of the root
        self.tokens: List[Token] = list(root.tokens)
        # buffer environments
        self._token_envs = [
            token.envs
            for token in self.tokens
        ]

    def __iter__(self) -> Iterator[LatexToken]:
        lower = str.lower if self.lower else lambda x: x
        for token, envs in zip(self.tokens, self._token_envs):
            if envs and '$' is envs[-1]:
                yield LatexToken(
                    lower(token.lexeme),
                    Range(
                        Position(*token.effective_range[0]),
                        Position(*token.effective_range[1])
                    ),
                    envs)
            else:
                begin = 0
                for split in self.words.finditer(token.lexeme):
                    split_spans = (
                        (begin, split.span()[0]),
                        split.span())
                    for span in split_spans:
                        span_text = token.lexeme[span[0]:span[-1]]
                        if span_text and not self.token_filter.fullmatch(span_text):
                            if self._perform_german_replacements:
                                span_text = _replace_german_characters(span_text)
                            yield LatexToken(
                                lower(span_text),
                                Range(
                                    Position(*token.parser.offset_to_position(token.begin+span[0])),
                                    Position(*token.parser.offset_to_position(token.begin+span[1]))
                                ),
                                envs)
                    begin = split.span()[-1]
                end = len(token.lexeme.rstrip())
                if begin != end:
                    rest_text = token.lexeme[begin:end]
                    if rest_text and not self.token_filter.fullmatch(rest_text):
                        if self._perform_german_replacements:
                            rest_text = _replace_german_characters(rest_text)
                        yield LatexToken(
                            lower(rest_text),
                            Range(
                                Position(*token.parser.offset_to_position(token.begin+begin)),
                                Position(*token.parser.offset_to_position(token.end+end))
                            ),
                            envs)

    @staticmethod
    def from_file(
        file: Union[str, LatexParser],
        lower: bool = True,
        lang: str = 'en',
        perform_character_replacements: bool = True) -> Optional[LatexTokenStream]:
        """ Constructs latex token stream from file or latex parser. Returns None if file failed to parse successfully. """
        if isinstance(file, str):
            file = LatexParser(file)
        assert isinstance(file, LatexParser)
        if not file.success:
            return None
        return LatexTokenStream(
            file.root,
            lang=lang,
            perform_character_replacements=perform_character_replacements,
            lower=lower)


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
