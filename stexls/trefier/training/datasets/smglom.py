import multiprocessing as mp
import os
import pickle
import re
import sys
from enum import IntEnum
from glob import glob
from pathlib import Path
from typing import Callable, List, Sequence, Tuple

from stexls.util import download
from stexls.latex import tokenizer

_TREFI_PATTERN = re.compile(r'[ma]*tref[ivx]+s?')
_DEFI_PATTERN = re.compile(r'[ma]*def[ivx]+s?')


class Label(IntEnum):
    ' Possible labels. '
    TEXT = 0
    TREFI = 1
    DEFI = 2


def load_and_cache(*args, cache: Path = Path('smglom.bin'), **kwargs):
    ''' Loads the dataset from cache if it exists,
        else loads the dataset using load() and writes
        the cache file with the given path if not None.
    Parameters:
        cache: Filename of the cache that will be generated.
        args: Forwarded to load(*args, **kwargs)
        kwargs: Forwarded to load(*args, **kwargs)
    Returns:
        Smglom x, y tuple.
    '''
    if cache and os.path.exists(cache):
        with open(cache, 'rb') as file:
            x, y = pickle.load(file)
        print('Loaded', len(x), 'files from cache.')
    else:
        print('File not cached. Loading...')
        x, y = load(*args, **kwargs)
        if cache:
            write_cache(x, y, path=cache)
    return x, y


def write_cache(x, y, path: Path = Path('smglom.bin'), force: bool = False):
    ' Helper that writes a (x, y) tuple to a file if it doesn\'t exist. '
    if not force and path.exists():
        raise ValueError(f'File {path} already exists.')
    with path.open('wb') as fd:
        pickle.dump((x, y), fd)


def load(
        download_dir: Path = Path('data'),
        lang: str = 'en',
        binary: bool = True,
        progress: Callable = None,
        limit: int = None) -> Tuple[List[List[str]], List[List[int]]]:
    ''' Loads smglom repositories as dataset. Files that fail to parse
        or parse with no tokens are ignored.
    Parameters:
        download_dir: Path to where the repositories should be downloaded to and loaded from.
        lang: Language of smglom files to use.
        binary: If True, uses binary labels [Text=0, Keyword=1] instead of [Text=0, Trefi=1, Defi=2].
        progress: Optional progress indicator callable.
        limit: Limit of the number of files being parsed.
    Returns:
        Tuple of list of lists of lexemes and list of lists of integer labels.
    '''
    files = [
        file
        for folder
        in maybe_download(download_dir=download_dir)
        for file
        in glob(os.path.join(folder, f'**/*.{lang}.tex'))
    ]
    files = files[:limit or len(files)]
    x = []
    y = []
    with mp.Pool() as pool:
        print('Parsing', len(files), 'files.')
        if progress:
            it = progress(pool.imap_unordered(
                tokenizer.LatexTokenizer.from_file, files))
        else:
            it = pool.map(tokenizer.LatexTokenizer.from_file, files)
        for i, latex_tokens in filter(None, enumerate(it)):
            tokens, labels = _parse_file(list(latex_tokens), binary)
            if not tokens:
                print(
                    'File', '"?"' if progress else files[i], 'failed to generate tokens.', file=sys.stderr)
            elif len(tokens) != len(labels):
                raise RuntimeError('Unexpected lengths for tokens (%i) and labels (%i).' % (
                    len(tokens), len(labels)))
            else:
                x.append(tokens)
                y.append(labels)
    return x, y


def maybe_download(download_dir: Path) -> List[str]:
    ''' Downloads smglom git repositories and returns the paths to them.
    Parameters:
        download_dir: Root directory to where the repositories should be cloned to.
            Appends 'smglom' automatically if not already at the end of the path.
    Returns:
        List of the paths of the downloaded repositories.
    '''
    repositories = [
        "physics",
        "cs",
        # "lmfdb",
        "probability",
        "measure-theory",
        "tannakian",
        "categories",
        "theresas-playground",
        "complexity",
        "arithmetics",
        "elliptic-curves",
        "manifolds",
        "numthy",
        "identities",
        "numthyfun",
        "constants",
        "analysis",
        "trigonometry",
        "numbers",
        "primes",
        "linear-algebra",
        "magic",
        "functional-analysis",
        "geometry",
        "topology",
        "calculus",
        "algebra",
        "graphs",
        "sets",
        "mv",
        "chevahir",
        "SMGloM"
    ]
    print('Saving repositories to', download_dir)
    paths = []
    for repo in repositories:
        try:
            paths.append(download.maybe_download_git(
                repo_url=os.path.join('https://gl.mathhub.info/smglom', repo),
                save_dir=download_dir))
        except Exception as e:
            print(f'Download of {repo} failed with:', e, file=sys.stderr)
    return paths


def _parse_file(tokens: List[tokenizer.LatexToken], binary: bool) -> Tuple[List[str], List[Label]]:
    ''' Parses a list of latex tokens into a tuple of lexemes and their labels
    Parameters:
        tokens: List of latex tokens of a file.
    Returns:
        2-Tuple with first member being the lexemes of valid tokens
        and the second member being their labels
    '''
    x = []
    y = []
    for token in tokens:
        x.append(token.lexeme)
        y.append(_envs2label(token.envs, binary))
    return x, y


def _envs2label(envs: Sequence[str], binary_labels: bool) -> Label:
    ' Determines label by looking a list of environments. '
    if any(map(_TREFI_PATTERN.fullmatch, envs)):
        return Label.TREFI
    if any(map(_DEFI_PATTERN.fullmatch, envs)):
        return Label.TREFI if binary_labels else Label.DEFI
    return Label.TEXT
