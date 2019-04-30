import scipy.stats as _stats
import collections as _collections

class ChiSquareModel:
    def __init__(self, X=None):
        """Initializes Chi-Square Model

        Calls fit(X) if X is not None.
        
        Keyword Arguments:
            X {list} -- List of documents of tokens
        """
        self.word_counts = None
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
        self.word_counts = _collections.Counter(word for doc in X for word in doc)

    def _chisquare(self, phrase_in_document, all_other_phrases_in_document, phrase_in_other_documents, all_other_phrases_in_all_other_documents, num_documents):
        statistic, p_value = _stats.chisquare([
            phrase_in_document, 
            all_other_phrases_in_document,
        ], [
            phrase_in_other_documents / num_documents,
            all_other_phrases_in_all_other_documents / num_documents
        ])
        return statistic
    
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
            for phrase, phrase_in_document in _collections.Counter(doc).items():
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
            result.append([transform[word] for word in doc])
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
            for phrase, phrase_in_document in _collections.Counter(doc).items():
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
            result.append([transform[word] for word in doc])
        return result
