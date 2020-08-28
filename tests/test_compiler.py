import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from stexls.vscode import *
from stexls.stex import *

mathhub = Path.home() / 'MathHub'
outdir = Path(TemporaryDirectory().name)

assert mathhub.is_dir()

class Tests:
    def test_trefii_without_module(self):
        file = mathhub / 'MiKoMH/TDM/source/vc/snip/diffpatch-intro.tex'
        assert file.is_file()
        c = Compiler(mathhub, outdir)
        obj = c.compile(file)
        obj.format()

    def test_inner_document_importmodule_link_order(self):
        # TODO: Muss pairs vor sets vor setoid vor semigroup erscheinen? Oder soll die Reihenfolge in der Sourcedatei egal sein?
        file = mathhub / 'MiKoMH/talks/source/sTeX/ex/sTeX-modules-ex.tex'
        assert file.is_file()
        compiler = Compiler(mathhub, outdir)
        obj = c.compile(file)
        obj.format()

Tests().test_trefii_without_module()