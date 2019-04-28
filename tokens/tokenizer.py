from collections import Counter, defaultdict
import re
import pickle
import TexSoup
import itertools
from os.path import isfile, join
from multiprocessing.pool import Pool
import pathlib
from functools import partial

class TokenizerFilters:
    # list of characters used to split the original text
    DEFAULT_DELIMETER = ' \n\t\r!"#$%&\'()*+,-./:;<=>?@[\\]^_`{|}~'
    DEFAULT_FILTER = DEFAULT_DELIMETER
    WHITESPACE_FILTER = ' \n\t\r'
    KEEP_MEANINGFUL_CHARACTERS = ' \n\t\r$%\'/<>@[\\]^`{|}~'

class Tokenizer:
    def __init__(self, word_count_dict=None, num_words=None, oov_token=None, **kwargs):
        if word_count_dict is not None:
            self.fit_count(word_count_dict, num_words, oov_token, **kwargs)
    
    @staticmethod
    def from_word_index(word_index_dict, num_words=None, oov_token='oov'):
        word_count_dict = {word:len(word_index_dict)-index for word, index in word_index_dict.items()}
        return Tokenizer(word_count_dict, num_words=num_words, oov_token=oov_token)
    
    def fit_count(self, word_count_dict, num_words=None, oov_token=None, case_sensitive=False, delimeters=TokenizerFilters.DEFAULT_DELIMETER, filter_list=TokenizerFilters.DEFAULT_FILTER):
        """
        Fits the tokenizer to a dictionary of word counts
            :param self: Tokenizer
            :param word_count_dict: Dictionary of tokens and appearence count
            :param num_words=None: Maximum number of words or None for all
            :param oov_token=None: Token to be used for out of vocabulary tokens or None if oov tokens should be ignored
            :param case_sensitive=False: If true, calls lower() on all tokens
            :param delimeters=TokenizerFilters.DEFAULT_DELIMETER: Delimeter to determine what are words
            :param filter_list=TokenizerFilters.DEFAULT_FILTER: List of characters that are filtered from the token stream
        """
        # create default filter settings if fit() was not called
        if not hasattr(self, 'delimeters') or not hasattr(self, 'filter_list'):
            if delimeters is None or filter_list is None:
                raise Exception("No delimeters or filter_list not provided, but fit() was not called.")
            filter_list = ''.join(c for c in filter_list if not c in word_count_dict)
            self._create_token_splitter_and_filter(delimeters, filter_list)
        # remember settings
        self.oov_token = (oov_token.lower() if case_sensitive else oov_token) if oov_token else None
        self.case_sensitive = case_sensitive
        self.word_count = word_count_dict
        # apply filter_list
        filtered_words = [(token,count) for token, count in sorted(self.word_count.items(), key=lambda kv: kv[1], reverse=True)]
        # remember num words
        self.num_words = min(num_words if num_words else len(filtered_words), len(filtered_words))
        # index the most common num_words words
        self.word_index = {token:index+1
                           for index, (token, count)
                           in zip(range(self.num_words), filtered_words)}
        if oov_token is not None:
            if oov_token in self.word_index:
                self.set_oov_index(self.word_index[oov_token])
            else:
                self.num_words += 1
                self.set_oov_index(self.num_words)
                self.word_count[oov_token] = sum(count for token, count in self.word_count.items() if token not in self.word_index)
        else:
            self.oov_index = None

        # create inverse mapping
        self.inv_word_index = {v:k for k,v in self.word_index.items()}
    
    def fit(self, X, num_words=None, oov_token=None, delimeters=TokenizerFilters.DEFAULT_DELIMETER, filter_list=' \n\t\r[]&\\/', case_sensitive=False, exclude_unique_tokens=True, document_of_tokens=False):
        """
        Fits the tokenizer to a list of string documents.
            :param self: Tokenizer
            :param X: List of documents
            :param num_words=None: Maximum amount of words recognized
            :param oov_token=None: Token to use for out of vocabulary words or None if they should be ignored
            :param delimeters=TokenizerFilters.DEFAULT_DELIMETER: List of characters which are used to split words
            :param filter_list=TokenizerFilters.DEFAULT_FILTER: List of characters which are not allowed to appear as tokens in the tokenstream
            :param case_sensitive=False: If true, lower() is called on all tokens
            :param exclude_unique_tokens=True: If true, excludes all tokens that appear only once
            :param document_of_tokens=False: If true, skips tokenization of each document
        """
        self.exclude_unique_tokens = exclude_unique_tokens
        self.case_sensitive = case_sensitive
        self._create_token_splitter_and_filter(delimeters, filter_list)

        if document_of_tokens:
            all_tokens = (token for doc in X for token in doc)
            if not case_sensitive:
                all_tokens = map(str.lower, all_tokens)
        else:
            all_tokens = (token for doc in self._apply_splitter_to_documents(X, return_indices=False) for token in doc)

        word_count = {token:count for token, count in Counter(all_tokens).items()
                      if (not exclude_unique_tokens or count > 1)
                      and (not self.filter.match(token) or document_of_tokens)} # 'or document_of_tokens' in order to add tokens that were in the source tokens to the index
        self.fit_count(word_count_dict=word_count, num_words=num_words, oov_token=oov_token, case_sensitive=case_sensitive, delimeters=None, filter_list=None)
    
    def transform(self, X, return_indices=False, document_of_tokens=False):
        """
        Transformas a list of documents into recognized tokens.
            :param self: Tokenizer
            :param X: List of documents
            :param return_indices=False: If true, also returns begin and end offsets for each token
            :param document_of_tokens=False: If true, skips tokenization of the documents
        """
        if document_of_tokens:
            tokens = X
            if not self.case_sensitive:
                tokens = [[token.lower() for token in doc] for doc in tokens]
        else:
            tokens = self._apply_splitter_to_documents(X, return_indices=return_indices)

        if return_indices:
            if document_of_tokens:
                return [[(self.get_representation(token), index) for index, token in enumerate(doc) if self._test_token_representable(token)] for doc in tokens]
            else:
                return [[(self.get_representation(token), b, e) for token, b, e in doc if self._test_token_representable(token)] for doc in tokens]
        else:
            return [[self.get_representation(token) for token in doc if self._test_token_representable(token)] for doc in tokens]

    def tokenize(self, X, return_indices=False, display_oov_words=False):
        """
        Only splits the documents into words.
            :param self: Tokenizer
            :param X: List of documents
            :param return_indices=False: If true, also returns begin and end offset of each token
            :param display_oov_words=True: if set to True, shows the original token instead of oov_token in case of oov words
        """   
        tokens = self._apply_splitter_to_documents(X, return_indices=return_indices)
        represent = lambda token: token if display_oov_words or token in self.word_index else self.oov_token
        if return_indices:
            return [[(represent(token), start, end) for token, start, end in doc if self._test_token_representable(token)] for doc in tokens]
        else:
            return [[represent(token) for token in doc if self._test_token_representable(token)] for doc in tokens]
    
    def get_representation(self, token):
        return self.word_index.get(token if self.case_sensitive else token.lower(), self.oov_index) # oov_index is None if no oov was specified

    def inverse_transform(self, y):
        """
        Transforms a documents of tokens back into words
            :param self: Tokenizer
            :param y: Transformed documents
        """
        return [[self.inv_word_index[token] if token in self.inv_word_index else self.oov_token
                for token in seq]
                for seq in y]
        
    def fit_transform(self, X, *fit_positional, **fit_named):
        self.fit(X, *fit_positional, **fit_named)
        return self.transform(X)

    def _create_token_splitter_and_filter(self, delimeters, filter_list):
        """
        :delimeters: delimeters used to split text into tokens
        :filter_list: filters token matching the any entry in the list
        """
        self.filter_list = filter_list
        base_filter = f"[{''.join(map(re.escape, filter_list))}]"
        self.filter = re.compile(base_filter)

        self.delimeters = delimeters
        base_splitter = f"([{''.join(map(re.escape, delimeters))}])"
        self.token_splitter = re.compile(base_splitter)

    def _apply_splitter_to_documents(self, X, return_indices):
        """
        :X: list of documents
        :return_indices: additionally return offset inside original document for each token
        :return: list of lists of tokens created by the tokenizer
        """
        # case sensitivity
        if not self.case_sensitive:
            X = map(str.lower, X)
        return list(map(lambda x: list(self._document_token_iterator(x, return_indices)), X))

    def _document_token_iterator(self, document, return_indices):
        """
        :document: a single document
        :return: list of tokens with their offset inside the given document
        """
        if return_indices:
            start = 0
            matches = map(lambda m: (m.group(), m.start(), m.end()), self.token_splitter.finditer(document))
            for (token, split, end) in matches:
                extract = document[start:split]
                if split > start:
                    yield (extract, start, split)
                if end > split:
                    yield (token, split, end)
                start = end
        else:
            for token in filter(len, self.token_splitter.split(document)):
                yield token

    def _test_token_representable(self, token):
        """
        :token: token to test
        :return: True if a not filtered token can be represented by either something in the word_index or the oov_token if specified
        """
        # valid if in wordindex
        if token in self.word_index:
            return True 
        
        # not valid if filterd
        match = self.filter.match(token)
        if match and len(token) == len(match.group()):
            return False

        # valid if oov token is specified
        if self.oov_token:
            return True

        # else invalid
        return False
    
    def set_oov_index(self, index=0):
        """
        :index: new index for oov tokens
        """
        assert(self.oov_token)
        self.oov_index = index
        self.word_index[self.oov_token] = index

    @staticmethod
    def to_file(tokenizer, path):
        with open(path, 'wb') as ref:
            return pickle.dump(tokenizer, ref)

    @staticmethod
    def from_file(path):
        with open(path, 'rb') as ref:
            return pickle.load(ref)

class TexTokenizer:
    def __init__(
        self,
        math_token='mathformula',
        delimeters=TokenizerFilters.DEFAULT_DELIMETER,
        filter_list=TokenizerFilters.KEEP_MEANINGFUL_CHARACTERS,
        exclude_unique_tokens=False):
        self.math_token = math_token
        self.delimeters = delimeters
        self.filter_list = filter_list
        self.exclude_unique_tokens = exclude_unique_tokens
        
    def transform(self, X, return_indices:bool=True, return_envs:bool=True, lower=False, subdocument_selector_function=lambda x:x, n_jobs=None):
        """Transforms tex documents into tokens with optional position offsets and applied environments
        
        Arguments:
            X {list} -- List of tex documents as strings or paths to tex documents
        
        Keyword Arguments:
            return_indices {bool} -- Optionally returns token positional data as (start, end) pairs (default: {True})
            return_envs {bool} -- Optionally returns applied environments for each token (default: {True})
            lower {bool} -- Option to call lower() on all documents loaded (default: {False})
            subdocument_selector_function {functor} -- Applies a function on valid tex documents before tokenizing them (default: {lambdax:x})
        
        Returns:
            list -- List of tokens for each document
        """
        def tokenize(document):
            """Tokenizes a tex document into its sub tokens"""
            self.documents.append(document)
            prev = None
            for token in document:
                if 'OArg' in token.envs:
                    prev = None
                    continue # skip OArgs
                for t in token.subtokens(self.delimeters, self.filter_list):
                    if '$' in t.envs and prev:
                        continue
                    prev = '$' in t.envs
                    yield t
        self.documents = []
        def success_and_record_document_length_distribution(x):
            if x.success and len(x.tokens):
                return True
            return False
        TexDocumentLowerBound = partial(TexDocument, lower=lower)
        if n_jobs is None or n_jobs <= 1:
            success_filtered = filter(success_and_record_document_length_distribution, map(TexDocumentLowerBound, X))
        else:
            with Pool(n_jobs) as pool:
                success_filtered = filter(success_and_record_document_length_distribution, pool.map(TexDocumentLowerBound, X))
        tokenized = map(tokenize, subdocument_selector_function(success_filtered))
        if return_indices and return_envs:
            return map(list, tokenized)
        def filter_features(document):
            if return_indices:
                return map(lambda x: x[:-1], document)
            elif return_envs:
                return map(lambda x: x[:1] + x[3:], document)
            else:
                return map(lambda x: x[0], document)
        return map(list, map(filter_features, tokenized))

