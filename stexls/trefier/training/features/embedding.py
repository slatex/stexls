from typing import Dict, Optional, Union, Iterable, List
import numpy as np
from sklearn.decomposition import PCA
from stexls.util import download

class GloVe:
    ' Implements transformation of tokens to glove embedding vectors. '
    def __init__(
        self,
        n_components: Optional[int] = None,
        oov_vector: Union['random', 'zero', None] = None,
        word_limit: Optional[int] = None,
        source_dim: int = 50,
        download_dir: str = '/tmp',
        extract_dir: str = None):
        ''' Initializes the embedding transform.
        Parameters:
            n_components: Performs PCA on the loaded embeddings to fit the given number of components.
            oov_vector: Method of how a oov token should be treated: 'random' or 'zero' vector or None to ignore.
            word_limit: Limits the number of words loaded from GloVe.
            source_dim: Identifier for source dimension of GloVe to load.
            download_dir: Specifies the directory in which the downloaded GloVe embedding should be saved.
            extract_dir: Optional path to where the contents of the downloaded zip file will be stored.
                If None, extracts the files to the same directory they were downloaded to.
        '''
        files = GloVe.maybe_download_and_extract(download_dir, extract_dir)
        for path in files:
            if f'{source_dim}d' in path:
                embeddings = GloVe.parse(path, limit=word_limit)
                if n_components and n_components < source_dim:
                    reduced = PCA(n_components).fit_transform(np.array(list(embeddings.values())))
                    self.embeddings = {
                        word: vector
                        for word, vector in zip(embeddings, reduced)
                    }
                else:
                    self.embeddings = embeddings
                self.vocab = list(self.embeddings)
        matrix = np.array(list(self.embeddings.values()))
        self.mean = matrix.mean()
        self.std = matrix.std()
        self.embedding_size = n_components or len(list(self.embeddings.values())[0])
        self.oov_vec = {
            'random': np.random.normal(self.mean, self.std, size=self.embedding_size),
            'zero': np.zeros(self.embedding_size),
        }.get(oov_vector)

    def transform(self, x: Iterable[Iterable[str]]) -> List[List[np.ndarray]]:
        ''' Transforms a list of lists of tokens to their respective GloVe embedding.
        Parameters:
            x: List of list of token lexemes.
        Returns:
            List of lists of the embeddings for those tokens.
        '''
        return [
            np.array([
                self.embeddings.get(word, self.oov_vec)
                for word in doc
                if self.oov_vec is not None or word in self.embeddings
            ])
            for doc in x
        ]

    @staticmethod
    def maybe_download_and_extract(download_dir: str, extract_dir: str = None):
        ' Maybe downloads and extracts pretrained glove embeddings to the specified directory. '
        return download.maybe_download_and_extract(
            "http://nlp.stanford.edu/data/glove.6B.zip",
            save_dir=download_dir,
            extract_dir=extract_dir)

    @staticmethod
    def parse(path: str, limit: int = None) -> Dict[str, np.ndarray]:
        ''' Parses a stanford glove embedding file.
        Parameters:
            path: Path to a stanford GloVe embedding file.
            limit: Optional limit of words used.
        Returns:
            Dictionary from words to an embedding vector.
        '''
        vectors = {}
        with open(path, 'r') as file:
            for i, line in enumerate(file.readlines()):
                if limit and limit <= i:
                    break
                word, *embedding = line.split()
                vectors[word] = np.array(embedding, dtype=np.float32)
        return vectors
