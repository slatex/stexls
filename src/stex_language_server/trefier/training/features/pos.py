from __future__ import annotations
from typing import List
import numpy as np
import nltk
from sklearn.preprocessing import LabelEncoder, OneHotEncoder
__all__ = ['PosTagModel']

class PosTagModel:
    def __init__(self):
        self.tagger = nltk.tag.PerceptronTagger()
        categories = np.unique(list(self.tagger.tagdict.values()))
        tags = OneHotEncoder(
            sparse=False,
            categories='auto'
        ).fit_transform(
            LabelEncoder().fit_transform(categories).reshape(-1, 1)
        )
        self.tag_indices = {
            label: tag
            for label, tag
            in zip(categories, tags)
        }
        self._UNK_tag = np.zeros(tags.shape[-1])
    
    def predict(self, sequences: List[List[str]]) -> List[List[int]]:
        return np.array([
            [
                self.tag_indices.get(tag, self._UNK_tag)
                for token, tag
                in nltk.pos_tag(seq)
            ]
            for seq in sequences
        ])
    
    @property
    def num_categories(self):
        return len(self._UNK_tag)
    
    def __setstate__(self, state):
        # restore state
        self.tag_indices, self._UNK_tag = state
        # create a new tagger
        self.tagger = nltk.tag.PerceptronTagger()
    
    def __getstate__(self):
        # do not store the tagger
        return self.tag_indices, self._UNK_tag
