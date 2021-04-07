from __future__ import annotations

import collections
from typing import Dict, Hashable, List, Sequence, TypeVar, Generic

import numpy as np

TokenType = TypeVar('TokenType', bound=Hashable)


class TfIdfModel(Generic[TokenType]):
    def __init__(self, ord: float = 1):
        """ Initializes a tf-idf transformer.

        Args:
            ord (float, optional): Output vector norm order. Defaults to 1.

        Generic Args:
            TokenType: Type of the tokens used to fit the model.
        """
        # Document frequencies: Number of documents a word appears in
        self.dfs: Dict[TokenType, int] = dict()
        # Inverse document frequencies
        self.idfs: Dict[TokenType, float] = dict()
        # Number of documents used to fit
        self.num_documents: int = 0
        # Norm
        self.ord: float = ord
        # Small epsilon value
        self.epsilon: float = 1e-12

    def vocab(self):
        return tuple(self.dfs)

    def fit(self, X: Sequence[Sequence[TokenType]], y=None) -> TfIdfModel:
        """Fit the model on a corpus.

        Args:
            X (Sequence[Sequence[TokenType]]): Corpus of documents, where each document is a sequence of tokens.
            y (Any, optional): Not used. Defaults to None.

        Returns:
            TfIdfModel: Self
        """
        self.num_documents = len(X)

        # document frequencies: Number of documents a word appears in
        self.dfs = dict(collections.Counter(
            [word for doc in X for word in set(doc)]))

        # inverse document frequncies
        self.idfs = {
            word: TfIdfModel.idf(self.num_documents, df)
            for word, df in self.dfs.items()
        }
        return self

    def fit_transform(self, X: Sequence[Sequence[TokenType]], y=None) -> List[List[float]]:
        """ Fit and transform the input corpus.

        This method fits each document in the corpus without any knowledge about the current document.
        Unlike using fit(X).transform(X), this method will remove the knowledge about the current document
        gained by fitting on it, before applying the transform.

        Args:
            X (Sequence[Sequence[TokenType]]): Input corpus of documents, where each document is a sequence of tokens.
            y (None, optional): Unused. Defaults to None.

        Returns:
            List[List[float]]: Each token in the original corpus is transformed to it's tf-idf representation.
        """
        self.fit(X)
        result = []
        for doc in X:
            tfs = TfIdfModel.tf(doc)
            vec = np.array([
                tfs[word] * TfIdfModel.idf(
                    self.num_documents - 1,
                    self.dfs[word] - 1
                )
                for word in doc
            ])
            if self.ord is not None:
                norm = np.linalg.norm(vec, ord=self.ord)
                if norm > 0:
                    vec /= norm
            result.append(vec.tolist())
        return result

    def transform(self, X: Sequence[Sequence[TokenType]], y=None) -> List[List[float]]:
        """ Transforms each token in the input corpus into it's tf-idf representation.

        Args:
            X (Sequence[Sequence[TokenType]]): Input corpus of documents, where each document is a sequence of tokens.
            y (None, optional): Unused. Defaults to None.

        Returns:
            List[List[float]]: Tokens of every document transformed into their tfidf representation.
        """
        result = []
        for doc in X:
            tfs = TfIdfModel.tf(doc)
            vec = np.array([
                tfs[word] * self.idfs.get(word, 0)
                for word in doc
            ])
            if self.ord is not None:
                vec /= np.linalg.norm(vec, ord=self.ord)
            result.append(vec.tolist())
        return result

    @staticmethod
    def idf(num_documents: int, document_frequency: int) -> float:
        """ Computes the inverse document frequency (idf) of a single term given it's document frequency
        and the number of documents in the corpus.

        Args:
            num_documents (int): Number of documents in the corpus.
            document_frequency (int): Number of occurrences of some term in a single document.

        Returns:
            float: idf value for the unnamed term.
        """
        if 0 in (num_documents, document_frequency):
            return 0
        return np.log2(float(num_documents) / document_frequency)

    @staticmethod
    def tf(document: Sequence[TokenType]) -> Dict[TokenType, float]:
        """ Computes the term frequency for each token in the input document.

        Args:
            document (Sequence[TokenType]): Single input document, given as a sequence of it's tokens.

        Returns:
            Dict[TokenType, float]: Dictionary mapping from token lexeme to the lexeme's term frequency in this document.
        """
        doc_len = len(document)
        return {
            word: term_count / doc_len
            for word, term_count
            in collections.Counter(document).items()
        }
