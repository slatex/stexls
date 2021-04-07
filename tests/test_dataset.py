from tempfile import TemporaryDirectory
from unittest import TestCase

from stexls.trefier.dataset import SmglomDataset
from stexls.trefier.preprocessing import PreprocessedDataset, Preprocessor


class TestSmglomDataset(TestCase):

    def test_collate_batch(self):
        with TemporaryDirectory() as tmpdir:
            smglom = SmglomDataset(
                tmpdir, train=False, download=True)
            prep = Preprocessor()
            ds: PreprocessedDataset = prep.fit_transform(
                smglom.documents, [list(map(int, t)) for t in smglom.targets])
            batch = [ds[i] for i in range(len(ds))]
            batch_size = len(batch)
            max_length = max(len(sample[0]) for sample in batch)
            lengths, tokens, key, tfidf, targets = ds.collate_fn(batch)
            self.assertEqual(max_length, max(lengths))
            self.assertTupleEqual(tokens.shape, (batch_size, max_length))
            self.assertTupleEqual(key.shape, (batch_size, max_length, 1))
            self.assertTupleEqual(tfidf.shape, (batch_size, max_length, 1))
            self.assertTupleEqual(targets.shape, (batch_size, max_length, 1))
