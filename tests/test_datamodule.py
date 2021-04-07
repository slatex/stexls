from unittest import TestCase
from tempfile import TemporaryDirectory


from stexls.trefier.dataset import SmglomDataModule


class TestDataModule(TestCase):
    def test_dataloader(self):
        with TemporaryDirectory() as tempdir:
            batch_size = 32
            dm = SmglomDataModule(
                batch_size=batch_size,
                num_workers=0,
                data_dir=tempdir
            )
            dm.prepare_data()
            dm.setup('test')
            dl = dm.test_dataloader()
            it = iter(dl)
            batch = next(it)
            lengths, tokens, keyphraseness, tfidf, targets = batch
            max_length = int(max(lengths))
            self.assertEqual(lengths.shape, (batch_size,))
            self.assertEqual(tokens.shape, (batch_size, max_length))
            self.assertEqual(keyphraseness.shape, (batch_size, max_length, 1))
            self.assertEqual(tfidf.shape, (batch_size, max_length, 1))
            self.assertEqual(targets.shape, (batch_size, max_length, 1))
