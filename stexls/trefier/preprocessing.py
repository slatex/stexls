from pathlib import Path
import pickle

import torch
from torch.functional import Tensor
from torch.nn.utils.rnn import pad_sequence
from torch.utils.data.dataset import Dataset
from stexls.util.latex.parser import LatexParser
from typing import List, Optional, Sequence, Union
from dataclasses import dataclass

from ..util.latex.tokenizer import LatexTokenizer
from .keyphraseness import KeyphrasenessModel
from .tfidf import TfIdfModel
from .vocab import Vocab


@dataclass
class PreprocessedDataset(Dataset):
    tokens: Sequence[Sequence[int]]
    keyphraseness: Sequence[Sequence[float]]
    tfidf: Sequence[Sequence[float]]
    targets: Optional[Sequence[Sequence[int]]] = None

    def __len__(self):
        return len(self.tokens)

    def __getitem__(self, index):
        item = (
            self.tokens[index],
            self.keyphraseness[index],
            self.tfidf[index],
        )
        if self.targets is not None:
            item += (self.targets[index],)
        return item

    @staticmethod
    def collate_fn(batch):
        batch = list(
            sorted(batch, key=lambda x: len(x[0]), reverse=True))
        lengths = torch.tensor(
            list(map(lambda x: len(x[0]), batch)))
        features = zip(*batch)  # transpose
        padded_features: List[Tensor] = []
        for feature in features:
            padded_feature = pad_sequence(
                list(map(torch.tensor, feature)), batch_first=True)
            # add feature dimension, only if feature is not the tokens
            # indicated by an empty padded_features list
            if len(padded_features):
                padded_feature = padded_feature.unsqueeze(-1)
            padded_features.append(padded_feature)
        return (lengths, *padded_features)


class Preprocessor:
    def __init__(self, max_num_tokens: int = None) -> None:
        self.max_num_tokens = max_num_tokens
        self.vocab = Vocab(max_num_tokens=self.max_num_tokens)
        self.keyphraseness = KeyphrasenessModel[str, int]()
        self.tfidf = TfIdfModel[str]()

    def save(self, file: Path):
        with file.open('wb') as fd:
            pickle.dump(self, fd)

    @staticmethod
    def load(self, file: Path):
        with file.open('rb') as fd:
            return pickle.load(fd)

    def fit_transform(
            self,
            documents: Sequence[Sequence[str]],
            targets: Sequence[Sequence[int]]):
        self.vocab = Vocab(
            max_num_tokens=self.max_num_tokens).update_vocab(documents)
        tokens = [[self.vocab[token] for token in doc] for doc in documents]
        key = self.keyphraseness.fit_transform(documents, targets)
        tfidf = self.tfidf.fit_transform(documents)
        return PreprocessedDataset(tokens, key, tfidf, targets)

    def transform(
            self, documents: Sequence[Sequence[str]], targets: Sequence[Sequence[int]] = None):
        tokens = [[self.vocab[token] for token in doc] for doc in documents]
        key = self.keyphraseness.transform(documents)
        tfidf = self.tfidf.transform(documents)
        return PreprocessedDataset(tokens, key, tfidf, targets)

    def preprocess_files(self, *files: Union[str, Path, LatexParser]):
        documents = []
        for file in files:
            tokenizer = LatexTokenizer.from_file(file)
            if tokenizer is None:
                return []
            tokens = [token.lexeme for token in tokenizer.tokens()]
            documents.append(tokens)
        return self.transform(documents)
