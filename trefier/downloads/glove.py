# visit https://nlp.stanford.edu/projects/glove/ for information

import numpy as np
from sklearn.manifold import LocallyLinearEmbedding as LLE
from sklearn.decomposition import PCA
from keras.layers import Embedding

from . import download

__all__ = ['maybe_download_and_extract', 'load']

def maybe_download_and_extract():
    return download.maybe_download_and_extract("http://nlp.stanford.edu/data/glove.6B.zip")

def load_raw(embedding_dim:int, num_words:int=None, vocabulary:set=None):
    """Loads the raw glove embedding from file
    Arguments:
        :param embedding_dim: Which precomputed dimension to load (50, 100, 300).
        :param num_words: Maximum number of words to use load. None for all.
        :param vocabulary: Which words to include or None for all.
    Returns:
        Index from token to embedding vector and a list of tokens that were excluded
        because they were not in the vocabulary.
    """
    embeddings_index = {}
    oov_words = []
    # load the file with the specified embedding_dim
    files = maybe_download_and_extract()
    for embeddings_file in filter(lambda x: f'{embedding_dim}d' in x, files):
        with open(embeddings_file) as ref:
            # get the embedded word and coefficients in each line
            for line in ref:
                values = line.split()
                word = values[0]
                if vocabulary is not None and word not in vocabulary:
                    oov_words.append(word)
                    continue
                coefs = np.asarray(values[1:], dtype='float32')
                embeddings_index[word] = coefs
                if num_words is not None and len(embeddings_index) >= num_words:
                    break
        return embeddings_index, oov_words
    raise Exception("Could not find embedding file with dimensionality %i: Found %s" % (embedding_dim, files))

def load(
    embedding_dim:int,
    oov_token:str='<oov>',
    num_words:int=None,
    vocabulary:set=None,
    perform_pca:bool=False,
    perform_lle:bool=False,
    make_keras_layer:bool=True,
    max_sequence_length:int=None,
    **kwargs):
    """Loads or downloads glove embeddings

    Arguments:
        :param embedding_dim: Source embedding dimensionality to load.
        :param oov_token: If specified, adds a random vector for oov tokens.
        :param max_sequence_length: Max length for the keras layer.
        :param num_words: Maximum number of words to load. None loads all words.
        :param perform_pca: Wether pca should be performed.
        :param perform_lle: Wether lle should be performed.
        :param make_keras_layer: If set to true, also returns a keras Embedding layer that uses the loaded embedding matrix.

    Keyword Arguments:
        Arguments passed to the selected dimensionality reduction algorithm.
        Algorithms are:
        perform_lle for sklearn.manifold.LocallyLinearEmbedding(**kwargs)
        perform_pca for sklearn.decomposition.PCA(**kwargs)

    Returns:
        Triple of word index, the original embedding vectors as a numpy matrix and a keras Embedding layer (if make_keras_layer enabled)
        The word index is the mapping from a token to its index in the embedding matrix.
    """

    if perform_pca and perform_lle:
        raise Exception("PCA and LLE can't be performed at the same time.")

    embeddings_index, oov_words = load_raw(embedding_dim, num_words, vocabulary)

    if vocabulary is None:
        print(f"{len(embeddings_index)} embedding vectors loaded.")
    else:
        print(f"{len(embeddings_index)} embedding vectors loaded {len(oov_words)} words not in vocabulary")

    # create an one indexed word_index dictionary
    word_index = {word:index+1 for index, word in enumerate(embeddings_index)}

    # create matrix of known embeddings
    embedding_matrix = np.array(list(embeddings_index.values()))

    # do dimensionality reduction on known embeddings
    if perform_pca:
        embedding_matrix = PCA(**kwargs).fit_transform(embedding_matrix)
        embedding_dim = embedding_matrix.shape[1]
    
    if perform_lle:
        embedding_matrix = LLE(**kwargs).fit_transform(embedding_matrix)
        embedding_dim = embedding_matrix.shape[1]

    # add zero vector
    embedding_matrix = np.concatenate([
        np.zeros((1, *embedding_matrix.shape[1:])),
        embedding_matrix])
    
    if oov_token is not None:
        word_index[oov_token] = len(word_index) + 1
        # add a random vector at the end
        embedding_matrix = np.concatenate([
            embedding_matrix,
            np.random.normal(size=(1, *embedding_matrix.shape[1:]))])
    
    num_words = len(word_index)
            
    # create the untrainable keras layer
    if make_keras_layer:
        embedding_layer = Embedding(num_words + 1,
                                    embedding_dim,
                                    weights=[embedding_matrix],
                                    input_length=max_sequence_length,
                                    trainable=False)

        return word_index, embedding_matrix, embedding_layer
    else:
        return word_index, embedding_matrix