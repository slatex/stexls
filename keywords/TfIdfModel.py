import numpy as _np
import collections as _collections

class TfIdfModel:
    def __init__(self, X=None, normalize=True):
        self.dfs = None
        self.idfs = None
        self._num_documents:int = None
        self._epsilon = 1e-12
        self.normalize = normalize
        if X is not None:
            self.fit(X)

    @property
    def vocab(self):
        return set(self.dfs)
        
    def _idf(self, num_documents, document_frequency):
        """Calculates the IDF value for phrase
        
        Arguments:
            num_documents {int} -- Number of documents in the corpus
            document_frequency {int} -- Count of documents that use a phrase
        
        Returns:
            float -- Idf value for a phrase
        """
        return _np.log2(float(num_documents) / document_frequency)

    def _tf(self, term_frequency, document_length):
        """Calculates term frequency
        
        Arguments:
            term_frequency {int} -- Count of a term in a document
            document_length {int} -- Length of the document
        
        Returns:
            float -- Tf-Idf value of the word
        """

        return term_frequency / document_length

    def fit(self, X):
        """Fits the model
        
        Arguments:
            X {list} -- List of documents of tokens
        """
        self.dfs = _collections.defaultdict(int)
        self.idfs = {}
        self._num_documents = len(X)
        for doc in X:
            for word in set(doc):
                self.dfs[word] += 1

        for word, df in self.dfs.items():
            self.idfs[word] = self._idf(self._num_documents, df)

    def fit_transform(self, X):
        """Fits and transforms a corpus

        Each transformed document is treated as if it was not part of the fitting process
        
        Arguments:
            X {list} -- List of lists of tokens
        
        Returns:
            list -- Tfidf values for all tokens in all documents or 0 for unknown words
        """

        self.fit(X)
        result = []
        for doc in X:
            term_counts = _collections.Counter(doc)
            tfs = {word:self._tf(count, len(doc)) for word, count in term_counts.items()}
            vec = _np.array([
                tfs[word] * self._idf(self._num_documents - 1, self.dfs[word] - 1)
                if self.dfs[word] > 1 else 0
                for word in doc
            ], dtype=_np.float32)
            if self.normalize:
                vec /= _np.linalg.norm(vec)
            result.append(vec)
        return result

    def transform(self, X):
        result = []
        for doc in X:
            tfs = {word:self._tf(count, len(doc)) for word, count in _collections.Counter(doc).items()}
            result.append([
                tfs[word] * self.idfs.get(word, 0)
                for word in doc
            ])
        return result