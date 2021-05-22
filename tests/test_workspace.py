from pathlib import Path
from tempfile import NamedTemporaryFile
from unittest import TestCase

from stexls.util.workspace import Workspace


class TestWorkspace(TestCase):
    def test_workspace(self):
        root = Path.home() / 'source/stexls/downloads'
        with NamedTemporaryFile('w+') as fd:
            fd.write('MiKoMH')
            fd.flush()
            ws = Workspace(root, fd.name)
            files = ws.files
            self.assertGreater(len(files), 0)
            for file in files:
                match = ws.ignorefile.match(file)
                self.assertFalse(match)
