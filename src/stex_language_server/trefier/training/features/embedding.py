from typing import Dict, Optional, Union, Iterable, List
import numpy as np
from sklearn.decomposition import PCA
from stex_language_server.util import download

class GloVe:
    def __init__(
        self,
        n_components: Optional[int] = None,
        oov_vector: Union['random', 'zero', None] = None,
        word_limit: Optional[int] = None,
        datadir: str = 'data/',
        source_dim: int = 50):
        files = GloVe.maybe_download_and_extract(datadir)
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
        return [
            np.array([
                self.embeddings.get(word, self.oov_vec)
                for word in doc
            ])
            for doc in x
        ]

    @staticmethod
    def maybe_download_and_extract(downloaddir: str = 'data/'):
        return download.maybe_download_and_extract(
            "http://nlp.stanford.edu/data/glove.6B.zip",
            save_dir=downloaddir)

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