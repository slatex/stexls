from . import download as _download

test_url = 'https://www.clips.uantwerpen.be/conll2000/chunking/test.txt.gz'
train_url = 'https://www.clips.uantwerpen.be/conll2000/chunking/train.txt.gz'

def maybe_download_and_extract(silent=False):
    return (
        _download.maybe_download_and_extract(train_url, silent=silent),
        _download.maybe_download_and_extract(test_url, silent=silent),
    )

def _parse(path):
    with open(path) as ref:
        lines = map(str.split, map(str.rstrip, ref))
        sentences, sentence = [], []
        pos_tags, pos_doc = [], []
        for line in lines:
            if len(line):
                sentence.append(line[0])
                pos_doc.append(line[1])
            else:
                sentences.append(sentence)
                pos_tags.append(pos_doc)
                sentence, pos_doc = [], []
    return pos_tags, sentences

def load(return_sentences=True, silent=False):
    train_path, test_path = maybe_download_and_extract(silent=silent)
    train_pos_tags, train_sentences = _parse(train_path)
    test_pos_tags, test_sentences = _parse(test_path)
    if return_sentences:
        return ((train_sentences, train_pos_tags), (test_sentences, test_pos_tags))
    return train_pos_tags, test_pos_tags
