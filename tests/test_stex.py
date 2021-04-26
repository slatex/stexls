from stexls.stex.symbols import ModuleType
from stexls.stex.diagnostics import DiagnosticCodeName
import tempfile as tf
from pathlib import Path
from unittest import TestCase
from stexls.stex.compiler import Compiler


class MockGlossary:
    def __init__(self) -> None:
        self.dir = tf.TemporaryDirectory()
        self.root = Path(self.dir.name)

    def __enter__(self):
        return self

    def __exit__(self, *args, **kwargs):
        self.cleanup()

    def cleanup(self):
        self.dir.cleanup()


class MockRepository:
    def __init__(self, glossary: MockGlossary, name: str = None) -> None:
        self.glossary = glossary
        if name is None:
            name = tf.TemporaryDirectory(dir=glossary.root).name
        self.source = glossary.root / name / 'source'
        self.source.mkdir(parents=True, exist_ok=False)


class MockSourceFile:
    def __init__(self, repo: MockRepository, filename: str = None) -> None:
        self.repo = repo
        if filename is None:
            with tf.NamedTemporaryFile('x', delete=False, dir=repo.source, suffix='.tex') as fd:
                filename = fd.name
        self.path = (self.repo.source / filename).with_suffix('.tex')

    @property
    def root(self):
        return self.repo.glossary.root


class TestCompiler(TestCase):
    def setUp(self) -> None:
        self.dir = tf.TemporaryDirectory()
        self.root = Path(self.dir.name)
        self.repo_name = 'git-repository'
        self.source = self.root / self.repo_name / 'source'
        self.file = self.source / f'{self.repo_name}.en.tex'
        self.source.mkdir(parents=True)
        self.file.touch()

    def tearDown(self) -> None:
        self.dir.cleanup()

    def test_compile_mhmodnl(self):
        self.file.write_text(
            rf'\begin{{mhmodnl}}{{{self.repo_name}}}{{en}}\end{{mhmodnl}}')
        compiler = Compiler(self.root, self.source)
        obj = compiler.compile(self.file)
        self.assertEqual(obj.diagnostics.diagnostics, [])
        self.assertEqual(len(obj.references), 1)
        self.assertTupleEqual((self.repo_name,), obj.references[0].name)
        self.assertEqual(len(obj.dependencies), 1)
        self.assertEqual(obj.dependencies[0].module_name, self.repo_name)
        self.assertEqual(
            obj.dependencies[0].module_type_hint, ModuleType.MODSIG)
        self.assertEqual(len(obj.symbol_table.children), 1)
        self.assertEqual(len(obj.symbol_table.children[self.repo_name]), 1)
        module = obj.symbol_table.children[self.repo_name][0]
        self.assertTupleEqual(
            (self.repo_name,), module.qualified)

    def test_compile_defi(self):
        self.file.write_text(
            r'\begin{mhmodnl}{%s}{en}\defi{value}\end{mhmodnl}' % self.repo_name)
        compiler = Compiler(self.root, self.source)
        obj = compiler.compile(self.file)
        self.assertEqual(len(obj.references), 2)
        self.assertEqual(obj.references[0].name, (self.repo_name, ))
        self.assertEqual(obj.references[1].name, (self.repo_name, 'value'))
        self.assertEqual(len(obj.dependencies), 1)
        self.assertEqual(obj.dependencies[0].module_name, self.repo_name)
        self.assertEqual(
            obj.dependencies[0].module_type_hint, ModuleType.MODSIG)
        self.assertEqual(len(obj.symbol_table.children), 1)
        self.assertEqual(
            obj.symbol_table.children[self.repo_name][0].name, self.repo_name)
        self.assertListEqual(obj.diagnostics.diagnostics, [])

    def test_compile_aDefiiis(self):
        self.file.write_text(
            r'\begin{mhmodnl}{%s}{en}\aDefiiis{this value is ignored}{actual}{defi}{value}\end{mhmodnl}' % self.repo_name)
        compiler = Compiler(self.root, self.source)
        obj = compiler.compile(self.file)
        self.assertEqual(len(obj.references), 2)
        self.assertEqual(obj.references[0].name, (self.repo_name, ))
        self.assertEqual(obj.references[1].name,
                         (self.repo_name, 'actual-defi-value'))
        self.assertListEqual(obj.diagnostics.diagnostics, [])

    def test_compile_trefi(self):
        self.file.write_text(
            rf'\begin{{mhmodnl}}{{{self.repo_name}}}{{en}}\trefi{{value}}\end{{mhmodnl}}')
        compiler = Compiler(self.root, self.source)
        obj = compiler.compile(self.file)
        self.assertEqual(obj.diagnostics.diagnostics, [])
        self.assertEqual(len(obj.references), 2)
        self.assertTupleEqual((self.repo_name,), obj.references[0].name)
        self.assertTupleEqual((self.repo_name, 'value'),
                              obj.references[1].name)

    def test_compile_Trefvs(self):
        self.file.write_text(r'\Trefvs[target]{v}{a}{l}{u}{e}')
        compiler = Compiler(self.root, self.source)
        obj = compiler.compile(self.file)
        self.assertEqual(obj.diagnostics.diagnostics, [])
        self.assertTupleEqual(('target',), obj.references[0].name)
        self.assertTupleEqual(('target', 'v-a-l-u-e'), obj.references[1].name)

    def test_compile_mTrefiv(self):
        self.file.write_text(
            r'\mTrefiv[target?value]{ignored}{by}{optional}{arguments}')
        compiler = Compiler(self.root, self.source)
        obj = compiler.compile(self.file)
        self.assertEqual(len(obj.references), 2)
        self.assertTupleEqual(('target',), obj.references[0].name)
        self.assertTupleEqual(('target', 'value'), obj.references[1].name)
        self.assertEqual(len(obj.diagnostics.diagnostics), 1)
        self.assertEqual(
            obj.diagnostics.diagnostics[0].code, DiagnosticCodeName.MTREF_DEPRECATION_CHECK.value)

    def test_compile_atrefiii(self):
        self.file.write_text(
            r'\atrefiii[target]{this value is ignored}{a}{referenced}{value}')
        compiler = Compiler(self.root, self.source)
        obj = compiler.compile(self.file)
        self.assertEqual(len(obj.references), 2)
        self.assertTupleEqual(('target',), obj.references[0].name)
        self.assertTupleEqual(
            ('target', 'a-referenced-value'), obj.references[1].name)
        self.assertEqual(obj.diagnostics.diagnostics, [])
