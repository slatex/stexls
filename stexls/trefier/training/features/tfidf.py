from __future__ import annotations

import collections
from typing import Dict, Optional

import numpy as np


class TfIdfModel:
    def __init__(self, X=None, norm_order=1):
        """ Computes tfidf values for all tokens in the corpus X.
        Arguments:
            X: List of lists of tokens.
            norm_order: Order to normalize with or None for no normalization.
        """
        self.dfs: Optional[Dict[str, int]] = None
        self.idfs: Optional[Dict[str, float]] = None
        self._num_documents: Optional[int] = None
        self._epsilon: float = 1e-12
        self.norm_order: int = norm_order
        if X is not None:
            self.fit(X)

    @property
    def vocab(self):
        return set(self.dfs)

    def fit(self, X):
        """Fits the model

        Arguments:
            X {list} -- List of documents of tokens
        """
        self._num_documents = len(X)

        # document frequencies: Number of documents a word appears in
        self.dfs = dict(collections.Counter(
            [word for doc in X for word in set(doc)]))

        # inverse document frequncies
        self.idfs = {word: self._idf(self._num_documents, df)
                     for word, df in self.dfs.items()}

    def fit_transform(self, X):
        """Fits and transforms a corpus.

        Each transformed document is treated as if it was not part of the fitting process
        E.g.:

        def fit_transform(X):
            for doc in X:
                fit(X\\doc)
                yield transform(doc)
            fit(X)

        Arguments:
            X {list} -- List of lists of tokens

        Returns:
            list -- Tfidf values for all tokens in all documents or 0 for unknown words
        """

        self.fit(X)
        result = []
        for doc in X:
            tfs = self._tf(doc)
            vec = np.array([
                tfs[word] * self._idf(self._num_documents -
                                      1, self.dfs[word] - 1)
                for word in doc
            ])
            if self.norm_order is not None:
                vec /= np.linalg.norm(vec, ord=self.norm_order)
            result.append(vec)
        return result

    def transform(self, X):
        result = []
        for doc in X:
            tfs = self._tf(doc)
            vec = np.array([
                tfs[word] * self.idfs.get(word, 0)
                for word in doc
            ])
            if self.norm_order is not None:
                vec /= np.linalg.norm(vec, ord=self.norm_order)
            result.append(vec)
        return result

    @staticmethod
    def test_transform():
        X = ['this is document # 1 .'.split(), 'this is document number 2 .'.split(),
             'that is the doc number 3 .'.split()]

        t1 = TfIdfModel(X[1:]).transform([X[0]])[0]
        t2 = TfIdfModel().fit_transform(X)[0]

        assert all(np.abs(x1 - x2) < 1e-6 for x1, x2 in zip(t1, t2)
                   ), "transform() and fit_transform() result not equal."

    def _idf(self, num_documents: int, document_frequency: int):
        """Calculates the inverse-document-frequency value for phrase.

        Arguments:
            num_documents {int} -- Number of documents in the corpus
            document_frequency {int} -- Count of documents that use a phrase

        Returns:
            float -- Idf value for a phrase. Returns 0 if document_frequency is <=0
        """
        if document_frequency <= 0:
            return 0
        return np.log2(float(num_documents) / document_frequency)

    def _tf(self, doc):
        """Calculates term frequency of all words in a document.

        Arguments:
            doc: Document

        Returns:
            Dict of term frequencies
        """
        doc_len = len(doc)
        return {word: term_count / doc_len for word, term_count in collections.Counter(doc).items()}
