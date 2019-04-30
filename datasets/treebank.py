
from ..downloads import treebank as _download

def _parse(path, lower):
    with open(path) as file:
        sentences, sentence = [], []
        pos_tags, pos_doc = [], []
        for line in map(str.split, map(str.rstrip, file)):
            if len(line):
                word = line[0]
                sentence.append(word.lower() if lower else word)
                pos_doc.append(line[1])
            else:
                sentences.append(sentence)
                pos_tags.append(pos_doc)
                sentence, pos_doc = [], []
    return pos_tags, sentences

def load(lower=True, return_sentences=True, save_dir='data/', silent=False):
    train_path, test_path = _download.maybe_download_and_extract(save_dir=save_dir, silent=silent)
    train_pos_tags, train_sentences = _parse(train_path, lower=lower)
    test_pos_tags, test_sentences = _parse(test_path, lower=lower)
    if return_sentences:
        return ((train_sentences, train_pos_tags), (test_sentences, test_pos_tags))
    return train_pos_tags, test_pos_tags
