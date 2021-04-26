import tempfile as tf
from pathlib import Path
from unittest import TestCase

from stexls.stex.compiler import Compiler
from stexls.stex.diagnostics import DiagnosticCodeName
from stexls.stex.symbols import ModuleType


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
        self.module_name = 'module-name'
        self.source = self.root / self.repo_name / 'source'
        self.file = self.source / f'{self.module_name}.en.tex'
        self.module = self.source / f'{self.module_name}.tex'
        self.source.mkdir(parents=True)
        self.file.touch()
        self.module.touch()

    def tearDown(self) -> None:
        self.dir.cleanup()

    def test_compile_mhmodnl(self):
        self.file.write_text(
            rf'\begin{{mhmodnl}}{{{self.module_name}}}{{en}}\end{{mhmodnl}}')
        compiler = Compiler(self.root, self.source)
        obj = compiler.compile(self.file)
        self.assertEqual(obj.diagnostics.diagnostics, [])
        self.assertEqual(len(obj.references), 1)
        self.assertTupleEqual((self.module_name,), obj.references[0].name)
        self.assertEqual(len(obj.dependencies), 1)
        self.assertEqual(obj.dependencies[0].module_name, self.module_name)
        self.assertEqual(
            obj.dependencies[0].module_type_hint, ModuleType.MODSIG)
        self.assertEqual(len(obj.symbol_table.children), 1)
        self.assertEqual(len(obj.symbol_table.children[self.module_name]), 1)
        module = obj.symbol_table.children[self.module_name][0]
        self.assertTupleEqual(
            (self.module_name,), module.qualified)

    def test_compile_defi(self):
        self.file.write_text(
            r'''\begin{mhmodnl}{%s}{en}
            \defi{value}
            \end{mhmodnl}''' % self.module_name)
        compiler = Compiler(self.root, self.source)
        obj = compiler.compile(self.file)
        self.assertEqual(len(obj.references), 2)
        self.assertEqual(obj.references[0].name, (self.module_name, ))
        self.assertEqual(obj.references[1].name, (self.module_name, 'value'))
        self.assertEqual(len(obj.dependencies), 1)
        self.assertEqual(obj.dependencies[0].module_name, self.module_name)
        self.assertEqual(
            obj.dependencies[0].module_type_hint, ModuleType.MODSIG)
        self.assertEqual(len(obj.symbol_table.children), 1)
        self.assertEqual(
            obj.symbol_table.children[self.module_name][0].name, self.module_name)
        self.assertListEqual(obj.diagnostics.diagnostics, [])

    def test_compile_defi_name_oarg(self):
        self.file.write_text(
            r'''\begin{mhmodnl}{%s}{en}
            \adefv[name=value]{ignored}{this}{value}{will}{be}{ignored}
            \end{mhmodnl}''' % self.module_name)
        compiler = Compiler(self.root, self.source)
        obj = compiler.compile(self.file)
        self.assertEqual(len(obj.references), 2)
        self.assertEqual(obj.references[0].name, (self.module_name, ))
        self.assertEqual(obj.references[1].name, (self.module_name, 'value'))

    def test_compile_aDefiiis(self):
        self.file.write_text(
            r'''\begin{mhmodnl}{%s}{en}
            \aDefiiis{this value is ignored}{actual}{defi}{value}
            \end{mhmodnl}''' % self.module_name)
        compiler = Compiler(self.root, self.source)
        obj = compiler.compile(self.file)
        self.assertEqual(len(obj.references), 2)
        self.assertEqual(obj.references[0].name, (self.module_name, ))
        self.assertEqual(obj.references[1].name,
                         (self.module_name, 'actual-defi-value'))
        self.assertListEqual(obj.diagnostics.diagnostics, [])

    def test_compile_trefi(self):
        self.file.write_text(
            rf'\begin{{mhmodnl}}{{{self.module_name}}}{{en}}\trefi{{value}}\end{{mhmodnl}}')
        compiler = Compiler(self.root, self.source)
        obj = compiler.compile(self.file)
        self.assertEqual(obj.diagnostics.diagnostics, [])
        self.assertEqual(len(obj.references), 2)
        self.assertTupleEqual((self.module_name,), obj.references[0].name)
        self.assertTupleEqual((self.module_name, 'value'),
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

    def test_compile_modsig(self):
        self.module.write_text(
            r'\begin{modsig}{%s}\end{modsig}' % self.module_name)
        obj = Compiler(self.root, self.source).compile(self.module)
        sym, = obj.symbol_table.find((self.module_name,))
        self.assertEqual(sym.name, self.module_name)
        self.assertEqual(len(obj.symbol_table.children), 1)

    def test_compile_symi(self):
        self.module.write_text(
            r'''\begin{modsig}{%s}
            \symi{value}
            \end{modsig}''' % self.module_name)
        obj = Compiler(self.root, self.source).compile(self.module)
        sym, = obj.symbol_table.find((self.module_name, 'value'))
        self.assertEqual(sym.name, 'value')
        self.assertListEqual(obj.diagnostics.diagnostics, [])

    def test_compile_symdef(self):
        self.module.write_text(
            r'''\begin{modsig}{%s}
            \symdef{value}
            \end{modsig}''' % self.module_name)
        obj = Compiler(self.root, self.source).compile(self.module)
        sym, = obj.symbol_table.find((self.module_name, 'value'))
        self.assertEqual(sym.name, 'value')
        self.assertListEqual(obj.diagnostics.diagnostics, [])

    def test_compile_duplicate_symdef(self):
        self.module.write_text(
            r'''\begin{modsig}{%s}
            \symdef{value}
            \symdef{value}
            \end{modsig}''' % self.module_name)
        obj = Compiler(self.root, self.source).compile(self.module)
        sym1, sym2, = obj.symbol_table.find((self.module_name, 'value'))
        self.assertEqual(sym1.name, 'value')
        self.assertEqual(sym2.name, 'value')
        self.assertListEqual(obj.diagnostics.diagnostics, [])

    def test_compile_symdef_name(self):
        self.module.write_text(
            r'''\begin{modsig}{%s}
            \symdef[name=value]{argument will be ignored}
            \end{modsig}''' % self.module_name)
        obj = Compiler(self.root, self.source).compile(self.module)
        sym, = obj.symbol_table.find((self.module_name, 'value'))
        self.assertEqual(sym.name, 'value')
        self.assertListEqual(obj.diagnostics.diagnostics, [])

    def test_compile_gimport(self):
        self.module.write_text(
            r'''\begin{modsig}{%s}
            \gimport{value}
            \end{modsig}''' % self.module_name)
        obj = Compiler(self.root, self.source).compile(self.module)
        dep, = obj.dependencies
        self.assertEqual(dep.file_hint, self.source / 'value.tex')
        self.assertEqual(dep.module_name, 'value')
        ref, = obj.references
        self.assertTupleEqual(ref.name, ('value',))
        self.assertListEqual(obj.diagnostics.diagnostics, [])

    def test_compile_gimport_oarg(self):
        self.module.write_text(
            r'''\begin{modsig}{%s}
            \gimport[path/to/repo]{value}
            \end{modsig}''' % self.module_name)
        obj = Compiler(self.root, self.source).compile(self.module)
        dep, = obj.dependencies
        self.assertEqual(
            dep.file_hint, self.root / 'path/to/repo/source/value.tex')
        self.assertEqual(dep.module_name, 'value')
        ref, = obj.references
        self.assertTupleEqual(ref.name, ('value',))
        self.assertListEqual(obj.diagnostics.diagnostics, [])

    def test_cant_infer_referenced_module(self):
        self.file.write_text(r'\trefi{value}')
        obj = Compiler(self.root, self.source).compile(self.file)
        diag, = obj.diagnostics.diagnostics
        self.assertEqual(
            diag.code,
            DiagnosticCodeName.CANT_INFER_REF_MODULE_OUTSIDE_MODULE.value)

    def test_duplicate_symbol(self):
        self.module.write_text(
            r'''\begin{modsig}{%s}
            \symi{value}
            \symi{value}
            \end{modsig}''' % self.module_name)
        obj = Compiler(self.root, self.source).compile(self.module)
        diag, = obj.diagnostics.diagnostics
        self.assertEqual(
            diag.code,
            DiagnosticCodeName.DUPLICATE_SYMBOL.value)

    def test_parser_exception(self):
        self.file.write_text(r'\trefi{')
        obj = Compiler(self.root, self.source).compile(self.file)
        diag, = obj.diagnostics.diagnostics
        self.assertEqual(
            diag.code,
            DiagnosticCodeName.PARSER_EXCEPTION.value)

    def test_module_file_mismatch(self):
        self.module.write_text(
            r'''\begin{modsig}{wrong module name}\end{modsig}''')
        obj = Compiler(self.root, self.source).compile(self.module)
        diag, = obj.diagnostics.diagnostics
        self.assertEqual(
            diag.code,
            DiagnosticCodeName.MODULE_FILE_NAME_MISMATCH.value)

    def test_mtref_deprecation(self):
        self.file.write_text(
            r'''\begin{mhmodnl}{%s}{en}
                \mtrefi[?value]{deprecated mtrefi}
            \end{mhmodnl}''' % self.module_name)
        obj = Compiler(self.root, self.source).compile(self.file)
        diag, = obj.diagnostics.diagnostics
        self.assertEqual(
            diag.code,
            DiagnosticCodeName.MTREF_DEPRECATION_CHECK.value)

    def test_mtref_question_mark(self):
        self.file.write_text(
            r'''\begin{mhmodnl}{%s}{en}
                \mtrefi{questionmark missing}
            \end{mhmodnl}''' % self.module_name)
        obj = Compiler(self.root, self.source).compile(self.file)
        codes = set(diag.code for diag in obj.diagnostics.diagnostics)
        self.assertEqual(len(codes), 2)
        self.assertIn(
            DiagnosticCodeName.MTREF_DEPRECATION_CHECK.value,
            codes)
        self.assertIn(
            DiagnosticCodeName.MTREF_QUESTIONMARK_CHECK.value,
            codes)
