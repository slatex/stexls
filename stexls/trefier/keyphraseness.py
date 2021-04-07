from __future__ import annotations
from typing import Dict, Generic, Hashable, List, Iterable, TypeVar
import collections

__all__ = ['KeyphrasenessModel']


TokenType = TypeVar('TokenType', bound=Hashable)
TargetType = TypeVar('TargetType')


class KeyphrasenessModel(Generic[TokenType, TargetType]):
    def __init__(self):
        """Initialized keyphraseness model.

        The model calculates *keyphraseness* with the following formula:

            P(keyword|W) = count(D_key) / count(D_w)

        The probability, that a term W is a keyword is equal to
        the number of times the term W is a keyword, divided
        by the number of times it appears in any document

        Generic Arguments:
            TokenType: Type of the tokens used to fit the model. Usually str.
            TargetType: Target type. Usually int.
                But can be anything that can be checked implicitly for truthyness.
        """
        self.keyphraseness: Dict[TokenType, float] = {}
        self.dfs: Dict[TokenType, float] = {}
        self.kfs: Dict[TokenType, int] = {}

    def vocab(self):
        return set(self.dfs)

    def fit(self, X: Iterable[Iterable[TokenType]], y: Iterable[Iterable[TargetType]]) -> KeyphrasenessModel:
        """ Fits the model to a given corpus X and token-wise attached labels y.

        Args:
            X (Iterable[Iterable[TokenType]]): A corpus of documents, where each document is a sequence of tokens.
            y (Iterable[Iterable[TargetType]]): Target labels for each token.
                Only the truthyness of each label is used to decide if it is a keyword or not.
                Falsy labels are "not keyword", while truthy keywords are treated as "keyword".

        Returns:
            KeyphrasenessModel: self
        """
        for doc, labels in zip(X, y):
            for word in set(doc):
                self.dfs.setdefault(word, 0)
                self.dfs[word] += 1
            keywords = (word for word, label in zip(doc, labels) if label)
            for word, count in collections.Counter(keywords).items():
                self.kfs.setdefault(word, 0)
                self.kfs[word] += count
        for word in self.dfs:
            self.keyphraseness[word] = self.kfs.get(word, 0) / self.dfs[word]
        return self

    def fit_transform(
            self,
            X: Iterable[Iterable[TokenType]],
            y: Iterable[Iterable[TargetType]]
    ) -> List[List[float]]:
        r""" Fits the model to the given corpus (X, y).

        This combined method transforms each keyword in X as if it was not part
        of the fitting process prior to it.

        E.g.:
        After self.fit(X, y) we transform each x_n in X as if self.fit(X \ x_n, y \ y_n) was called,
        where "\" represents the "without" operation.

        Args:
            X (Iterable[Iterable[TokenType]]): Input corpus of documents of tokens.
            y (Iterable[Iterable[TargetType]]): Target labels for each token.
                Only the truthyness of each label is used to decide if it is a keyword or not.
                Falsy labels are "not keyword", while truthy keywords are treated as "keyword".

        Returns:
            Iterable[Iterable[float]]: Keyphraseness for each token.
                Keyphraseness is an alias for float.
        """
        self.fit(X, y)
        result = []
        for doc, labels in zip(X, y):
            keywords = collections.Counter(
                word for word, label in zip(doc, labels) if label != 0)
            result.append([
                (
                    self.kfs.get(word, 0) - keywords.get(word, 0)
                ) / (self.dfs[word] - 1)
                if self.dfs[word] > 1
                else 0
                for word in doc
            ])
        return result

    def transform(self, X: Iterable[Iterable[TokenType]], y=None) -> List[List[float]]:
        """ Transforms each token in the input corpus into it's keyphraseness value.

        Args:
            X (Iterable[Iterable[TokenType]]): Input documents made up of tokens.
            y (Any, optional): Unused. Defaults to None.

        Returns:
            List[List[float]]: Keyphraseness for each token.
                Keyphraseness is an alias for float.
        """
        return [
            [
                self.keyphraseness.get(word, 0) for word in doc
            ]
            for doc in X
        ]
