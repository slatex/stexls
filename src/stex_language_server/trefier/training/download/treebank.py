from stex_language_server.util import download

__all__ = ['maybe_download_and_extract']

def maybe_download_and_extract(save_dir='data/', silent=False):
    return (
        download.maybe_download_and_extract('https://www.clips.uantwerpen.be/conll2000/chunking/train.txt.gz', silent=silent, save_dir=save_dir),
        download.maybe_download_and_extract('https://www.clips.uantwerpen.be/conll2000/chunking/test.txt.gz', silent=silent, save_dir=save_dir),
    )
