from stex_language_server.util import download

class GloVe:
    def __init__(self, datadir: str = 'data/'):
        self.files = GloVe.maybe_download_and_extract(datadir)
    
    @staticmethod
    def maybe_download_and_extract(downloaddir: str = 'data/'):
        return download.maybe_download_and_extract(
            "http://nlp.stanford.edu/data/glove.6B.zip",
            save_dir=downloaddir)

