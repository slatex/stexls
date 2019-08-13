from __future__ import annotations
from typing import Union, Tuple, List, Optional, Iterable
from glob import glob
from os import path
from multiprocessing.pool import Pool
from enum import IntEnum
import re
from tqdm import tqdm

from trefier.downloads import smglom as download_smglom
from trefier.parser.latex_parser import LatexParser, Token

__all__ = ['Label', 'parse_files', 'parse_dataset']

class Label(IntEnum):
    """ Possible labels. """
    TEXT=0
    TREFI=1
    DEFI=2

def parse_files(
    lang: str = 'en',
    save_dir: str = 'data/',
    n_jobs: int = 4,
    silent: bool = False) -> List[LatexParser]:
    """ Downloads all smglom repositories from github and parses the .tex files for the specified language.

    Keyword Arguments:
        :param lang: Language of files to load. Uses the pattern: "filename.lang.tex".
        :param save_dir: Directory to where the git repositories are downloaded.
        :param n_jobs: Number of processes to use to parse tex files.
        :param silent: Uses tqdm to display loading progress.
    
    Returns:
        List of successfully parsed latex documents.
        
    """
    
    files = [
        file
        for folder
        in download_smglom.maybe_download(save_dir=save_dir, silent=silent)
        for file
        in glob(path.join(folder, f'**/*.{lang}.tex'))
    ]

    with Pool(n_jobs) as pool:
        if not silent:
            documents = [doc for doc in tqdm(pool.imap_unordered(LatexParser, files))]
        else:
            documents = pool.map(LatexParser, files)

    return list(filter(lambda doc: doc.success, documents))

def parse_dataset(
    documents: Optional[List[LatexParser]] = None,
    binary_labels: bool = False,
    math_token: str = '<math>',
    lower: bool = True,
    lang: Optional[str] = None) -> Tuple[List[List[str]], List[List[Label]]]:
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
    if documents is None:
        lang = lang or 'en'
        documents = parse_files(lang=lang)

    lower = str.lower if lower else lambda s: s

    def alt_edge_detector(tokens: Iterable[Token]) -> List[bool]:
        """ Transforms an iterable of tokens to a list of bools that are True on the first token of an adefi or atrefi. """
        tokens = tuple(tokens)
        matcher = re.compile(r'a(tr|d)efi+s?').fullmatch
        alt_token_envs = tuple(any(map(matcher, token.envs)) for token in tokens)
        f = [alt_token_envs[0]] + [
            (not p) and n
            for p, n in zip(alt_token_envs, alt_token_envs[1:])
        ]
        return f

    labeled_tokens = [
        [
            (
                lower(
                    math_token
                    if math_token
                    and '$' in token.envs
                    else token.lexeme
                ),
                _envs2label(
                    token.envs,
                    binary_labels
                )
            )
            for token
            in doc.subtoken_stream(lang=lang, token_filter_fn=alt_edge_detector)
        ]
        for doc in documents
    ]

    list_of_X_y_pairs = [
        list(zip(*labeled))
        for labeled in labeled_tokens
    ]

    X, y = list(zip(*list_of_X_y_pairs))

    return X, y


def _envs2label(envs, binary_labels):
    """ Determines label by looking a list of environments. """
    TREFI_PATTERN = re.compile(r"""[ma]*trefi+s?""")
    DEFI_PATTERN = re.compile(r"""[ma]*defi+s?""")
    if any(map(TREFI_PATTERN.fullmatch, envs)):
        return Label.TREFI
    if any(map(DEFI_PATTERN.fullmatch, envs)):
        return Label.TREFI if binary_labels else Label.DEFI
    return Label.TEXT

