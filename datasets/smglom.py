
from ..downloads import smglom as _download_smglom
from glob import glob as _glob
from os import path as _path
from ..tokens import TexDocument as _TexDocument
from multiprocessing import pool as _pool
from tqdm import tqdm as _tqdm
import re as _re
from enum import IntEnum as _IntEnum

class Label(_IntEnum):
    """ Possible labels. """
    TEXT=0
    TREFI=1
    DEFI=2

def _envs2label(envs, binary_labels):
    """ Determines label by looking a list of environments. """
    TREFI_PATTERN = _re.compile(r"""[ma]*trefi+s?""")
    DEFI_PATTERN = _re.compile(r"""[ma]*defi+s?""")
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
    # Else find a* trefi/defis in this document
    for alt in doc.find_all('m?am?(tr|d)efi+s?', pattern=True):
        for _, alt_begin, alt_end, envs in alt:
            # ignore preceding OArgs and only use the first RArg
            if 'RArg' in envs: 
                # Ignore token between 'begin' and 'end' if it is contained inside the first token of an 'a*' symbol
                return alt_begin <= begin and end <= alt_end
    return False

def load(binary_labels=False, lang='en', save_dir='data/', n_jobs=4, silent=False):
    """ First step of loading smglom dataset.
        Downloads all smglom repositories from github and parses the .tex files for the specified language.
        After the documents have been parsed, use parse() in order to parse the tokens and associated labels in each file.

    Keyword Arguments:
        :param binary_labels: Replaces DEFI label with TREFI label if set to true.
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
        in _download_smglom.maybe_download(save_dir=save_dir, silent=silent)
        for file
        in _glob(_path.join(folder, f'**/*.{lang}.tex'))
    ]

    with _pool.Pool(n_jobs) as pool:
        if not silent:
            documents = [doc for doc in _tqdm(pool.imap_unordered(_TexDocument, files))]
        else:
            documents = pool.map(_TexDocument, files)
    
    return list(filter(lambda doc: doc.success, documents))

def parse(documents, return_X_y=True)
    """ Parses labels and tokens from TexDocuments
    
    Arguments:
        :param documents: List of TexDocuments.
    
    Keyword Arguments:
        :param return_X_y: Returns a tuple of X (tokens) and y (labels) if set to true.
    
    Returns:
        List of documents of (token, label) pair lists.
        To return a single pair X, y use the return_X_y argument.
    """
    labeled_tokens = [
        [
            (lexeme, _envs2label(envs, binary_labels))
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
