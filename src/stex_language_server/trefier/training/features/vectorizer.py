from typing import Iterable, Dict, List
import numpy as np
from collections import Counter

__all__ = ['CountVectorizer']

class CountVectorizer:
    def __init__(self):
        self.word_counts: Dict[str, int] = None
        self.word_index: Dict[str, int] = None
        self.vocab: Iterable[str] = None
    
    def fit_on_tokens(self, documents: Iterable[Iterable[str]]):
        self.word_counts = Counter(a for b in documents for a in b)
        self.word_index = {
            word: index + 1
            for index, (word, count)
            in enumerate(
                sorted(
                    self.word_counts.items(),
                    key=lambda x: x[1],
                    reverse=True))
        }
        self.vocab = tuple(self.word_counts)
    
    def transform(self, documents: Iterable[Iterable[str]]) -> List[List[int]]:
        return [
            [
                self.word_index[word]
                for word in doc
            ]
            for doc in documents
        ]
    
    def inverse_transform(self, sequences: Iterable[Iterable[int]]) -> List[List[str]]:
        inverse = {
            b: a
            for a, b in self.word_index.items()
        }
        return [
            [
                inverse[i]
                for i in seq
            ]
            for seq in sequences
        ]
    
    def fit_transform(self, documents: Iterable[Iterable[str]]) -> List[List[int]]:
        self.fit_on_tokens(documents)
        return self.transform(documents)
