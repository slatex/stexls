from . import download as _download

def maybe_download_and_extract(save_dir='data/', silent=False):
    return (
        _download.maybe_download_and_extract('https://www.clips.uantwerpen.be/conll2000/chunking/train.txt.gz', silent=silent, save_dir=save_dir),
        _download.maybe_download_and_extract('https://www.clips.uantwerpen.be/conll2000/chunking/test.txt.gz', silent=silent, save_dir=save_dir),
    )
