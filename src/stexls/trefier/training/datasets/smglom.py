from typing import Tuple, List
from enum import IntEnum
from glob import glob
import os
import re
import pickle
import multiprocessing as mp

from stexls.util import download
from stexls.util.latex import tokenizer

_TREFI_PATTERN = re.compile(r'[ma]*tref[ivx]+s?')
_DEFI_PATTERN = re.compile(r'[ma]*def[ivx]+s?')


class Label(IntEnum):
    ' Possible labels. '
    TEXT=0
    TREFI=1
    DEFI=2

def load_and_cache(cache: str = '/home/marian/smglom.bin', progress: callable = None):
    ''' Loads the dataset from cache if it exists,
        else loads the dataset using load() and writes
        the cache file with the given path if not None.
    Returns:
        Smglom x, y tuple.
    '''
    if cache and os.path.exists(cache):
        with open(cache, 'rb') as file:
            x, y = pickle.load(file)
        print('Loaded', len(x), 'files from cache.')
    else:
        print('File not cached. Loading...')
        x, y = load(progress=progress)
        if cache:
            write_cache(x, y, path=cache)
    return x, y

def write_cache(x, y, path: str = '/home/marian/smglom.bin', force: bool = False):
    ' Helper that writes a (x, y) tuple to a file if it doesn\'t exist. '
    if not force and os.path.exists(path):
        raise ValueError(f'File {path} already exists.')
    with open(path, 'wb') as file:
        pickle.dump((x, y), file)

def load(download_dir: str = 'data/', lang: str = 'en', binary: bool = True, progress: callable = None, limit: int = None):
    ''' Loads smglom repositories as dataset.
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
        in maybe_download(dest_dir=download_dir)
        for file
        in glob(os.path.join(folder, f'**/*.{lang}.tex'))
    ]
    progress = progress or (lambda x: x)
    x = []
    y = []
    with mp.Pool() as pool:
        for file in progress(pool.imap_unordered(tokenizer.LatexTokenizer.from_file, files[:limit or len(files)])):
            if file is None:
                continue
            tokens, labels = _parse_file(list(file), binary)
            x.append(tokens)
            y.append(labels)
        
    return x, y

def maybe_download(dest_dir: str = 'data/'):
    ''' Downloads smglom git repositories and returns the paths to them.
    Parameters:
        dest_dir: Root directory to where the repositories should be cloned to.
    Returns:
        List of the paths of the downloaded repositories.
    '''
    repositories = [
        "physics",
        "cs",
        #"lmfdb",
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
    save_dir = dest_dir if dest_dir.endswith('/smglom') else os.path.join(dest_dir, 'smglom')
    print('Saving repositories to', save_dir)
    paths = []
    for repo in repositories:
        try:
            paths.append(download.maybe_download_git(
                repo_url=os.path.join('https://gl.mathhub.info/smglom', repo),
                save_dir=save_dir))
        except Exception as e:
            print(f'Download of {repo} failed with:', e)
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
    for lexeme, _, _, envs in tokens:
        x.append(lexeme)
        y.append(_envs2label(envs, binary))
    return x, y

def _envs2label(envs: List[str], binary_labels: bool) -> Label:
    ' Determines label by looking a list of environments. '
    if any(map(_TREFI_PATTERN.fullmatch, envs)):
        return Label.TREFI
    if any(map(_DEFI_PATTERN.fullmatch, envs)):
        return Label.TREFI if binary_labels else Label.DEFI
    return Label.TEXT