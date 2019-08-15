from __future__ import annotations
import numpy as np
import collections
from scipy import stats

class ChiSquareModel:
    def __init__(self, X=None, norm_order=1):
        """Initializes Chi-Square Model

        Calls fit(X) if X is not None.
        
        Keyword Arguments:
            X: List of documents of tokens
            norm_order: Normal order or None for no normalization.
        """
        self.word_counts = None
        self.norm_order = norm_order
        if X is not None:
            self.fit(X)

    @property
    def vocab(self):
        return set(self.word_counts)
    
    def fit(self, X):
        """Fits the model to the dataset
        
        Arguments:
            X {list} -- List of documents of tokens
        """
        self._num_documents = len(X)
        self.word_counts = collections.Counter(word for doc in X for word in doc)
    
    def transform(self, X):
        """Transforms a list of documents to chi-sq values
        
        Arguments:
            X {list} -- List of documents of tokens
        
        Returns:
            list -- Chi-Square values for all tokens in all documents provided in X
        """

        result = []
        for doc in X:
            transform = {}
            for phrase, phrase_in_document in collections.Counter(doc).items():
                all_other_phrases_in_document = len(doc) - phrase_in_document
                phrase_in_other_documents = self.word_counts.get(phrase, 0)
                all_other_phrases_in_all_other_documents = sum(self.word_counts.values()) - phrase_in_other_documents
                if phrase_in_other_documents <= 0:
                    value = 0
                else:
                    value = self._chisquare(
                        phrase_in_document,
                        all_other_phrases_in_document,
                        phrase_in_other_documents,
                        all_other_phrases_in_all_other_documents,
                        self._num_documents)
                transform[phrase] = value
            
            vec = np.array([transform[word] for word in doc])
            if self.norm_order is not None:
                vec /= np.linalg.norm(vec, ord=self.norm_order)
            result.append(vec)
        return result
    
    def fit_transform(self, X):
        """Fits the model to X, then transforms all documents D_i as if D_i was not element of X during the fitting process
        
        Arguments:
            X {list} -- List of documents of tokens
        
        Returns:
            list -- Chi-Sq values for all tokens in all documents
        """
        self.fit(X)
        result = []
        for doc in X:
            transform = {}
            for phrase, phrase_in_document in collections.Counter(doc).items():
                all_other_phrases_in_document = (len(doc) - phrase_in_document)
                phrase_in_other_documents = self.word_counts[phrase] - phrase_in_document
                all_other_phrases_in_all_other_documents = sum(self.word_counts.values()) - len(doc)
                if phrase_in_other_documents <= 0:
                    value = 0
                else:
                    value = self._chisquare(
                        phrase_in_document,
                        all_other_phrases_in_document,
                        phrase_in_other_documents,
                        all_other_phrases_in_all_other_documents,
                        self._num_documents - 1)
                transform[phrase] = value
            vec = np.array([transform[word] for word in doc])
            if self.norm_order is not None:
                vec /= np.linalg.norm(vec, ord=self.norm_order)
            result.append(vec)
        return result
    
    @staticmethod
    def test_transform():
        X = ['this is document # 1 .'.split(), 'this is document number 2 .'.split(), 'that is the doc number 3 .'.split()]

        t1 = ChiSquareModel(X[1:]).transform([X[0]])
        t2 = ChiSquareModel().fit_transform(X)[0]

        assert all(np.abs(x1 - x2) < 1e-6 for x1, x2 in zip(t1, t2)), "transform() and fit_transform() result not equal."

    def _chisquare(self, phrase_in_document, all_other_phrases_in_document, phrase_in_other_documents, all_other_phrases_in_all_other_documents, num_documents):
        statistic, p_value = stats.chisquare([
            phrase_in_document, 
            all_other_phrases_in_document,
        ], [
            phrase_in_other_documents / num_documents,
            all_other_phrases_in_all_other_documents / num_documents
        ])
        return statistic
