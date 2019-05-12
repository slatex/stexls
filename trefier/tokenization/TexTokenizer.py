from multiprocessing.pool import Pool
from functools import partial

from keras.preprocessing.text import Tokenizer

from .TexDocument import TexDocument
from .filters import TokenizerFilters

__all__ = ['TexTokenizer']

class TexTokenizer:
    def __init__(
        self,
        math_token='<MathFormula>',
        filters=TokenizerFilters.KEEP_MEANINGFUL_CHARACTERS,
        oov_token='<oov>',
        lower=True):
        self.tokenizer = Tokenizer(filters=filters, oov_token=oov_token, lower=lower)
        self.math_token = math_token
    
    def _parse_files_in_parallel(self, X, n_jobs):
        # parse documents in parallel
        with Pool(n_jobs) as pool:
            documents = pool.map(partial(TexDocument, lower=self.tokenizer.lower), X)
        
        # return all successfully parsed documents
        return list(filter(lambda doc: doc.success, documents))
    
    def _documents_to_texts(self, documents):
        """ Extracts the lexemes from the tex documents and optionally returns the offsets and environments
        
        Arguments:
            documents: The documents to extract texts/lexemes from
        
        Returns:
            Tuple of the texts and additionally returns the lexeme (begin, end) offset and the latex environment it appears in.
        """
        texts = [[
            self.math_token
            if self.math_token is not None
            and '$' in envs
            else lexeme
            for lexeme, _, _, envs in doc.tokens]
            for doc in documents
        ]

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

        return texts, offsets, envs
    
    def fit_on_files(self, X, n_jobs=4):
        """ Fits the tokenizer to a list of given documents X.
        Arguments:
            :param X: List of documents. A document can be given as a path or the raw string.
        """

        documents = self._parse_files_in_parallel(X=X, n_jobs=n_jobs)

        texts = self._documents_to_texts(documents)[0]

        self.tokenizer.fit_on_texts(texts)
    
    def files_to_sequences(self, X, return_offsets=False, return_envs=False, n_jobs=4):
        documents = self._parse_files_in_parallel(X=X, n_jobs=n_jobs)
       
        texts, offsets, envs = self._documents_to_texts(documents)

        sequences = self.tokenizer.texts_to_sequences(texts)

        if return_offsets and return_envs:
            return sequences, offsets, envs
        if return_offsets:
            return sequences, offsets
        if return_envs:
            return sequences, envs
        return sequences
