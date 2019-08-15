from __future__ import annotations
from typing import List, Dict
from collections import Counter

__all__ = ['IndexTokenizer']

class IndexTokenizer:
    def __init__(self, oov_token: str = '<oov>'):
        """ Instantiates a tokenizer that transforms a sequence of tokens into a sequence of indices representing the token
        """
        self.oov_token = oov_token
        self.document_frequency = None
        self.term_frequency = None
        self.word_index = None
    
    def transform(self, sequences: List[List[str]]) -> List[List[int]]:
        return [
            [
                self[token]
                for token in seq
            ]
            for seq in sequences
        ]
    
    def inverse_transform(self, indices: List[List[int]]) -> List[List[str]]:
        inv_index = self.inverse_word_index
        return [
            [
                inv_index.get(index, self.oov_token)
                for index in seq
            ]
            for seq in indices
        ]
    
    def fit_on_sequences(self, sequences: List[List[str]]):
        self.document_frequency = {}
        self.term_frequency = {}
        for sequence in sequences:
            for token, count in Counter(sequence).items():
                self.document_frequency.setdefault(token, 0)
                self.document_frequency[token] += 1
                self.term_frequency.setdefault(token, 0)
                self.term_frequency[token] += count
        self.word_index = {
            term: i+1
            for i, (term, count)
            in enumerate(
                sorted(
                    self.term_frequency.items(),
                    key=lambda el: el[1],
                    reverse=True
                )
            )
        }
        if self.oov_token:
            if self.oov_token in self.word_index and self.word_index[self.oov_token] != len(self.word_index):
                raise Exception(f"Chosen oov token (${self.oov_token}) already appears in the provided corpus (at ${self.word_index[self.oov_token]}) and can't be used (as ${len(self.word_index)}).")
            elif self.oov_token not in self.word_index:
                self.word_index[self.oov_token] = len(self.word_index) + 1
        return self

    def fit_on_word_index(self, word_index: Dict[str, int]) -> IndexTokenizer:
        return self.fit_on_word_count({
                token: i+1
                for i, (token, index)
                in enumerate(
                    sorted(
                        word_index.items(),
                        key=lambda el: el[1],
                        reverse=True
                    )
                )
            }
        )

    def fit_on_word_count(self, word_count: Dict[str, int]) -> IndexTokenizer:
        self.document_frequency = word_count.copy()
        self.term_frequency = word_count.copy()
        self.word_index = {
            term: i+1
            for i, (term, count)
            in enumerate(
                sorted(
                    self.term_frequency.items(),
                    key=lambda el: el[1],
                    reverse=True
                )
            )
        }
        if self.oov_token:
            if self.oov_token in self.word_index and self.word_index[self.oov_token] != len(self.word_index):
                raise Exception(f"Chosen oov token ({self.oov_token}) already appears in the provided corpus (at {self.word_index[self.oov_token]}) and can't be used (as {len(self.word_index)}).")
            elif self.oov_token not in self.word_index:
                self.word_index[self.oov_token] = len(self.word_index) + 1
        return self

    @property
    def inverse_word_index(self):
        return {index: token for token, index in self.word_index.items()}

    def __getitem__(self, i: str):
        return self.word_index.get(i, self.word_index.get(self.oov_token))

    def __iter__(self):
        yield from self.word_index
