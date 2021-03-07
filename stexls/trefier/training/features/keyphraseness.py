import collections

__all__ = ['KeyphrasenessModel']


class KeyphrasenessModel:
    def __init__(self, X=None, Y=None):
        """Initialized model

        The model calculates keyphraseness with the following formula:
        P(keyword|W) = count(D_key) / count(D_w)

        Probability, that a term W is a keyword is equal to
        the number of times the term W is a keyword, divided
        by the number of times it appears in any document

        The classes in Y are treated as
        label == 0: "W isn't a keyword", and
        label != 0: "W is a keyword".

        Fits if the model to arguments X and Y, if provided.

        Keyword Arguments:
            X {list} -- List of documents of tokens
            Y {list} -- List of documents of labels
        """
        self.keyphraseness = None
        self.dfs = None
        self.kfs = None
        if X and Y:
            self.fit(X, Y)

    @property
    def vocab(self):
        return set(self.dfs)

    def fit(self, X, Y):
        """Fits the model to the given database

        Arguments:
            X {list} -- List of documents of tokens
            Y {list} -- List of documents of labels
        """
        self.keyphraseness = {}
        self.dfs = collections.defaultdict(float)  # document frequency
        self.kfs = collections.defaultdict(int)  # keyphrase frequency
        for doc, labels in zip(X, Y):
            for word in set(doc):
                self.dfs[word] += 1
            keywords = (word for word, label in zip(doc, labels) if label != 0)
            for word, count in collections.Counter(keywords).items():
                self.kfs[word] += count
        for word in self.dfs:
            self.keyphraseness[word] = self.kfs[word] / self.dfs[word]

    def fit_transform(self, X, Y):
        """Fits the object and transforms all samples as if it was not included in the fitting process

        Arguments:
            X {list} -- List of documents of tokens
            Y {list} -- List of documents of labels

        Returns:
            Keyphraseness feature vector for all documents in X
        """

        self.fit(X, Y)
        result = []
        for doc, labels in zip(X, Y):
            keywords = collections.Counter(
                word for word, label in zip(doc, labels) if label != 0)
            result.append([
                (self.kfs[word] - keywords.get(word, 0)) / (self.dfs[word] - 1)
                if self.dfs[word] > 1 else 0
                for word in doc
            ])
        return result

    def transform(self, X):
        """Transforms a given list of documents according to the model

        Arguments:
            X {list} -- List of documents of tokens

        Returns:
            list -- Keyphraseness values for all tokens in all documents or 0 for unknown words
        """

        return [
            [self.keyphraseness.get(word, 0) for word in doc]
            for doc in X
        ]
