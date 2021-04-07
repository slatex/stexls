from tempfile import NamedTemporaryFile
from typing import Sequence
from unittest import TestCase

from stexls.trefier.preprocessing import Preprocessor


class TestPreprocessor(TestCase):
    def setUp(self) -> None:
        self.documents: Sequence[Sequence[str]] = [
            'hello , world !'.split(),
            'treat world as a keyphrase !'.split(),
            'Lorem ipsum dolor sit amet'.split(),
        ]
        self.targets: Sequence[Sequence[int]] = [
            [0, 0, 1, 0],
            [0, 1, 0, 0, 1, 0],
            [0, 0, 0, 0, 1],
        ]
        self.prep = Preprocessor()

    def test_fit(self):
        tensors = self.prep.fit_transform(self.documents, self.targets)
        self.assertEqual(len(tensors.tokens), 3)
        lengths = tuple(len(tokens) for tokens in tensors.tokens)
        self.assertTupleEqual(lengths, (4, 6, 5))
        self.assertListEqual(
            tensors.keyphraseness[0], [0, 0, 1., 0, ])
        self.assertListEqual(
            tensors.keyphraseness[1], [0, 1., 0, 0, 0, 0])
        self.assertListEqual(
            tensors.keyphraseness[2], [0, 0, 0, 0, 0])

    def test_transform(self):
        train = self.prep.fit_transform(self.documents, self.targets)
        val = self.prep.transform(self.documents)
        self.assertListEqual(
            train.keyphraseness[1], [0, 1., 0, 0, 0, 0])
        self.assertListEqual(  # transform does not ignore self
            val.keyphraseness[1], [0, 1., 0, 0, 1., 0])
        self.assertListEqual(train.tokens, val.tokens)
        self.assertIsNotNone(train.targets)
        self.assertIsNone(val.targets)

    def test_files(self):
        self.prep.fit_transform(self.documents, self.targets)
        with NamedTemporaryFile('w') as fd:
            fd.write(r"""Hello, World!""")
            fd.seek(0)
            out = self.prep.preprocess_files(fd.name)
        self.assertEqual(len(out.tokens), 1)
        self.assertEqual(len(out.tokens[0]), 4)
        self.assertListEqual(out.keyphraseness[0], [0, 0, 1, 0])

    def test_collate(self):
        ds = self.prep.fit_transform(self.documents, self.targets)
        batch = [ds[i] for i in range(len(ds))]
        lengths, tokens, key, tfidf, targets = ds.collate_fn(batch)
        batch_size = len(batch)
        max_length = max(tuple(lengths))
        self.assertEqual(max_length, 6)
        self.assertTupleEqual(tuple(lengths), (6, 5, 4))  # is sorted!
        self.assertTupleEqual(tokens.shape, (batch_size, max_length))
        self.assertTupleEqual(key.shape, (batch_size, max_length, 1))
        self.assertTupleEqual(tfidf.shape, (batch_size, max_length, 1))
        self.assertTupleEqual(targets.shape, (batch_size, max_length, 1))
