from multiprocessing.pool import Pool
from functools import partial
from itertools import chain

from keras.preprocessing.text import Tokenizer

from .TexDocument import TexDocument
from .filters import TokenizerFilters

__all__ = ['TexTokenizer']

class TexTokenizer(Tokenizer):
    def __init__(
        self,
        math_token='<math>',
        filters=TokenizerFilters.KEEP_MEANINGFUL_CHARACTERS,
        oov_token='<oov>',
        lower=True):
        super().__init__(filters=filters, oov_token=oov_token, lower=lower)
        self.math_token = math_token
    
    def _parse_files_in_parallel(self, X, n_jobs):
        # split pre-parsed tex documents from files
        already_parsed = filter(lambda x: isinstance(x, TexDocument), X)
        not_parsed = filter(lambda x: not isinstance(x, TexDocument), X)

        # parse documents in parallel
        with Pool(n_jobs) as pool:
            documents = pool.map(partial(TexDocument, lower=self.lower), not_parsed)
        
        # return all successfully parsed documents
        return list(filter(lambda doc: doc.success, chain(already_parsed, documents)))
    
    def tex_files_to_tokens(self, files, return_offsets_and_envs=False, n_jobs=4):
        documents = self._parse_files_in_parallel(X=files, n_jobs=n_jobs)

        tokens = [[
            self.math_token
            if self.math_token is not None
            and '$' in envs
            else lexeme
            for lexeme, _, _, envs in doc.tokens]
            for doc in documents
        ]

        if not return_offsets_and_envs:
            return tokens

        offsets = [[
            (begin, end)
            for _, begin, end, _ in doc.tokens]
            for doc in documents
        ]

        envs = [[
            envs
            for _, _, _, envs in doc.tokens]
            for doc in documents
        ]

        return tokens, offsets, envs
    
    def tokens_to_sequences(self, X):
        return [
            [
                self.word_index.get(token, self.word_index.get(self.oov_token, 0))
                for token in doc
            ] for doc in X
        ]
    
    def fit_on_tex_files(self, X, n_jobs=4):
        """ Fits the tokenizer to a list of given documents X.
        Arguments:
            :param X: List of documents. A document can be given as a path or the raw string.
        """
        texts = self.tex_files_to_tokens(files=X, n_jobs=n_jobs)

        self.fit_on_texts(texts)
    
    def tex_files_to_sequences(self, X, n_jobs=4, return_offsets_and_envs=False):
        documents = self._parse_files_in_parallel(X=X, n_jobs=n_jobs)
       
        texts, offsets, envs = self.tex_files_to_tokens(documents, return_offsets_and_envs=True)

        sequences = self.texts_to_sequences(texts)

        if return_offsets_and_envs:
            return sequences, offsets, envs
        else:
            return sequences
