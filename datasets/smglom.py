
from ..downloads import smglom as _download_smglom
from glob import glob as _glob
from os import path as _path
from ..tokens import TexDocument as _TexDocument
from multiprocessing import pool as _pool
from tqdm import tqdm as _tqdm
import re as _re
from enum import IntEnum as _IntEnum

class Label(_IntEnum):
    TEXT=0
    TREFI=1
    DEFI=2

def _envs2label(envs, binary_labels):
    TREFI_PATTERN = _re.compile(r"""[ma]*trefi+s?""")
    DEFI_PATTERN = _re.compile(r"""[ma]*defi+s?""")
    if any(map(TREFI_PATTERN.fullmatch, envs)):
        return Label.TREFI
    if any(map(DEFI_PATTERN.fullmatch, envs)):
        return Label.TREFI if binary_labels else Label.DEFI
    return Label.TEXT

def _is_ignore(doc, begin, end, envs):
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

def load(binary_labels=False, lang='en', save_dir='data/', return_X_y=False, return_original_documents=False, n_jobs=4, silent=False):
    
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
    
    documents = list(filter(lambda doc: doc.success, documents))

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
        if return_original_documents:
            return documents, list_of_X_y_pairs
        else:
            return list_of_X_y_pairs

    X, y = list(zip(*list_of_X_y_pairs))

    if return_original_documents:
        return documents, (X, y)
    else:
        return X, y
