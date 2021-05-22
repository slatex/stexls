from unittest import TestCase
from pathlib import Path
from tempfile import TemporaryDirectory

from stexls.util.ignorefile import IgnoreFile


class TestIgnoreFile(TestCase):
    def setUp(self) -> None:
        self.dir = TemporaryDirectory()
        self.root = Path(self.dir.name)
        self.ignorefile = self.root / '.ignorefile'
        dirs = ('a/aa/dir', 'a/bb/dir', 'b/aa/dir', 'b/bb/dir', 'c/cc')
        (self.root / 'root-file.txt').write_text('root file.')
        for dir in dirs:
            (self.root / dir).mkdir(parents=True)
            ((self.root / dir).parent / 'file0.txt').write_text('file 0 content!')
            (self.root / dir / 'file1.txt').write_text('file 1 content!')
            (self.root / dir / 'file2.txt').write_text('file 2 content!')

    def tearDown(self) -> None:
        self.dir.cleanup()

    def test_file(self):
        self.ignorefile.write_text(r'''
            a/*/dir
            ! a/aa
            file1.txt
            b/bb
        ''')
        igf = IgnoreFile(self.ignorefile)
        self.assertSetEqual(igf.ignored_paths, {
            (igf.root / 'a/bb/dir').as_posix(),
            (igf.root / 'b/bb').as_posix(),
            (igf.root / 'a/bb/dir/file1.txt').as_posix(),
            (igf.root / 'b/aa/dir/file1.txt').as_posix(),
            (igf.root / 'b/bb/dir/file1.txt').as_posix(),
            (igf.root / 'c/cc/file1.txt').as_posix(),
        })
        self.assertFalse(igf.match(igf.root))
        self.assertFalse(igf.match(igf.root / 'root-file.txt'))
        self.assertFalse(igf.match(igf.root / 'a'))
        self.assertFalse(igf.match(igf.root / 'a/aa'))
        self.assertFalse(igf.match(igf.root / 'a/aa/file0.txt'))
        self.assertFalse(igf.match(igf.root / 'a/aa/dir'))
        self.assertFalse(igf.match(igf.root / 'a/aa/dir/file1.txt'))
        self.assertFalse(igf.match(igf.root / 'a/aa/dir/file2.txt'))
        self.assertFalse(igf.match(igf.root / 'a/bb'))
        self.assertFalse(igf.match(igf.root / 'a/bb/file0.txt'))
        self.assertTrue(igf.match(igf.root / 'a/bb/dir'))
        self.assertTrue(igf.match(igf.root / 'a/bb/dir/file1.txt'))
        self.assertTrue(igf.match(igf.root / 'a/bb/dir/file2.txt'))
        self.assertFalse(igf.match(igf.root / 'b'))
        self.assertFalse(igf.match(igf.root / 'b/aa'))
        self.assertFalse(igf.match(igf.root / 'b/aa/file0.txt'))
        self.assertFalse(igf.match(igf.root / 'b/aa/dir'))
        self.assertTrue(igf.match(igf.root / 'b/aa/dir/file1.txt'))
        self.assertFalse(igf.match(igf.root / 'b/aa/dir/file2.txt'))
        self.assertTrue(igf.match(igf.root / 'b/bb'))
        self.assertTrue(igf.match(igf.root / 'b/bb/file0.txt'))
        self.assertTrue(igf.match(igf.root / 'b/bb/dir'))
        self.assertTrue(igf.match(igf.root / 'b/bb/dir/file1.txt'))
        self.assertTrue(igf.match(igf.root / 'b/bb/dir/file2.txt'))
        self.assertFalse(igf.match(igf.root / 'c/cc'))
        self.assertFalse(igf.match(igf.root / 'c/cc/file0.txt'))
        self.assertTrue(igf.match(igf.root / 'c/cc/file1.txt'))

        self.assertFalse(igf.match(igf.root / 'a/does/notexist'))
        self.assertFalse(igf.match(igf.root / 'a/does/dir/notexist'))
