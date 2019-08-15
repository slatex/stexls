from __future__ import annotations
from typing import Union, Tuple, List, Optional, Iterable, Iterator
from glob import glob
from os import path
from multiprocessing.pool import Pool
from enum import IntEnum
import re
from tqdm import tqdm
import functools

from trefier.downloads import smglom as download_smglom
from trefier.tokenization.latex import LatexParser, Token
from trefier.tokenization.streams import LatexTokenStream, LatexToken

__all__ = ['Label', 'parse_files', 'parse_dataset']

class Label(IntEnum):
    """ Possible labels. """
    TEXT=0
    TREFI=1
    DEFI=2


def _alt_edge_detector(tokens: Iterable[Token]) -> List[bool]:
    """ Transforms an iterable of tokens to a list of bools that are True on the first token of an adefi or atrefi. """
    tokens = tuple(tokens)
    matcher = re.compile(r'a(tr|d)efi+s?').fullmatch
    alt_token_envs = tuple(any(map(matcher, token.envs)) for token in tokens)
    f = [alt_token_envs[0]] + [
        (not p) and n
        for p, n in zip(alt_token_envs, alt_token_envs[1:])
    ]
    return f

def _make_stream(file: str, lang: str, lower: bool):
    """ Makes a filetered token stream from a file path """
    parser = LatexParser(file)
    if parser is None or not parser.success:
        return None
    return LatexTokenStream(
        root=parser.root,
        lang=lang,
        lower=lower,
        perform_character_replacements=False,
        token_filter_fn=_alt_edge_detector)

_TREFI_PATTERN = re.compile(r"""[ma]*trefi+s?""")
_DEFI_PATTERN = re.compile(r"""[ma]*defi+s?""")

def _envs2label(envs: Tuple[str, ...], binary_labels: bool) -> Label:
    """ Determines label by looking a list of environments. """
    if any(map(_TREFI_PATTERN.fullmatch, envs)):
        return Label.TREFI
    if any(map(_DEFI_PATTERN.fullmatch, envs)):
        return Label.TREFI if binary_labels else Label.DEFI
    return Label.TEXT

def parse_files(
    lang: str = 'en',
    lower: bool = True,
    save_dir: str = 'data/',
    n_jobs: int = 4,
    show_progress: bool = False) -> Iterator[LatexTokenStream]:
    """ Downloads all smglom repositories from github and parses the .tex files for the specified language.

    Keyword Arguments:
        :param lang: Language of files to load. Uses the pattern: "filename.lang.tex".
        :param lower: Enables token to lowercase transform.
        :param save_dir: Directory to where the git repositories are downloaded.
        :param n_jobs: Number of processes to use to parse tex files.
        :param show_progress: Uses tqdm to display loading progress.
    
    Returns:
        List of successfully parsed latex documents.
        
    """
    
    files = [
        file
        for folder
        in download_smglom.maybe_download(save_dir=save_dir, show_progress=show_progress)
        for file
        in glob(path.join(folder, f'**/*.{lang}.tex'))
    ]

    make_stream = functools.partial(_make_stream, lang=lang, lower=lower)

    with Pool(n_jobs) as pool:
        if show_progress:
            it = tqdm(pool.imap_unordered(make_stream, files))
        else:
            it = pool.map(make_stream, files)
        yield from filter(None, it)

def parse_dataset(
    document_token_streams: Optional[List[LatexTokenStream]] = None,
    binary_labels: bool = False,
    math_token: str = '<math>',
    lower: bool = True,
    lang: Optional[str] = None,
    show_progress: bool = False) -> Tuple[List[List[str]], List[List[Label]]]:
    """ Parses tex documents for labels and tokens assuming they are annotated
    with trefi and defi tags.

    Keyword Arguments:
        :param documents: List of documents to use for dataset creation. Downloads and parses smglom files, if None.
        :param binary_labels: If True, aliases TREFI and DEFI tags as a single KEYWORD tag with the ordinal value 1.    
        :param math_token: String to use instead of math tokens.
        :param lower: Enables lowercase transform of all tokens.
        :param lang: Language the files got parsed for. Changes the tokenization process depending on the value.
    Returns:
        Tuple of list of lists of tokens and list of lists of labels.
    """
    if document_token_streams is None:
        document_token_streams = parse_files(lang=lang or 'en', show_progress=show_progress, lower=lower)

    labeled_tokens = [
        [
            (
                (math_token
                if math_token
                and '$' in token.envs
                else token.lexeme),
                _envs2label(
                    token.envs,
                    binary_labels
                )
            )
            for token
            in token_stream
        ]
        for token_stream in document_token_streams
    ]

    list_of_X_y_pairs = [
        list(zip(*labeled))
        for labeled in labeled_tokens
    ]

    X, y = list(zip(*list_of_X_y_pairs))

    return X, y
