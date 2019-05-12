
from glob import glob
from os import path
from multiprocessing.pool import Pool
from enum import IntEnum
import re
from tqdm import tqdm

from ..downloads import smglom as download_smglom
from ..tokenization import TexDocument

__all__ = ['Label', 'load_documents', 'parse']

class Label(IntEnum):
    """ Possible labels. """
    TEXT=0
    TREFI=1
    DEFI=2

def load_documents(lang='en', save_dir='data/', n_jobs=4, silent=False):
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
            documents = [doc for doc in tqdm(pool.imap_unordered(TexDocument, files))]
        else:
            documents = pool.map(TexDocument, files)
    
    return list(filter(lambda doc: doc.success, documents))

def parse(documents, binary_labels=False, return_X_y=True, math_token='<MathFormula>', lower=True):
    """ Parses labels and tokens from TexDocuments
    
    Arguments:
        :param documents: List of TexDocuments.
    
    Keyword Arguments:
        :param binary_labels: Replaces DEFI label with TREFI label if set to true.
        :param return_X_y: Returns a tuple of X (tokens) and y (labels) if set to true.
        :param math_token: The token that replaces math. If None, nothing is replaced.
        :param lower: calls str.lower on all tokens if set to True.

    Returns:
        List of documents with (token, label) pairs or a tuple of all tokens X and all labels y
        depending on the return_X_y argument.
    """
    lower = str.lower if lower else lambda str: str

    labeled_tokens = [
        [
            (lower(math_token if math_token and '$' in envs else lexeme), _envs2label(envs, binary_labels))
            for (lexeme, begin, end, envs)
            in doc.tokens
            if not _is_ignore(doc, begin, end, envs)
        ]
        for doc in documents
    ]

    list_of_X_y_pairs = [
        list(zip(*labeled))
        for labeled in labeled_tokens
    ]

    if not return_X_y:
        return list_of_X_y_pairs

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

def _is_ignore(doc, begin, end, envs):
    """ Determines if the token between begin, end from the tex document doc should be ignored.
    Arguments:
        :param doc: TexDocument for reference.
        :param begin: Begin offset of the token to be ignored.
        :param end: End offset of the token to be ignored.
        :param envs: Environments of the token.
    Return:
        Returns True if the token between begin and end is to be ignored.
    """
    # Ignore all OArgs
    if 'OArg' in envs:
        return True
    # Ignore first argument of an 'a*' environment (e.g.: atrefii or madefis)
    for alt in doc.find_all('m?am?(tr|d)efi+s?', pattern=True):
        for _, alt_begin, alt_end, envs in alt:
            if 'RArg' in envs: 
                return alt_begin <= begin and end <= alt_end
    return False
