from unittest import TestCase

from stexls.stex.compiler import Compiler
from stexls.stex.diagnostics import DiagnosticCodeName
from stexls.stex.linker import Linker
from stexls.stex.parser import (DefiIntermediateParseTree, IntermediateParser,
                                ModnlIntermediateParseTree)
from stexls.stex.symbols import (BindingSymbol, DefSymbol, ModuleSymbol,
                                 ModuleType)

from tests.mock import MockGlossary


class TestCompiler(TestCase, MockGlossary):
    def setUp(self) -> None:
        self.setup()

    def tearDown(self) -> None:
        self.cleanup()

    def test_compile_mhmodnl(self):
        file = self.write_binding('')
        compiler = Compiler(self.root, self.source)
        obj = compiler.compile(file)
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
        file = self.write_binding(r'\defi{value}')
        compiler = Compiler(self.root, self.source)
        obj = compiler.compile(file)
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
        file = self.write_binding(
            r'\adefv[name=value]{ignored}{this}{value}{will}{be}{ignored}')
        compiler = Compiler(self.root, self.source)
        obj = compiler.compile(file)
        self.assertEqual(len(obj.references), 2)
        self.assertEqual(obj.references[0].name, (self.module_name, ))
        self.assertEqual(obj.references[1].name, (self.module_name, 'value'))

    def test_compile_aDefiiis(self):
        file = self.write_binding(
            r'\aDefiiis{this value is ignored}{actual}{defi}{value}')
        compiler = Compiler(self.root, self.source)
        obj = compiler.compile(file)
        self.assertEqual(len(obj.references), 2)
        self.assertEqual(obj.references[0].name, (self.module_name, ))
        self.assertEqual(obj.references[1].name,
                         (self.module_name, 'actual-defi-value'))
        self.assertListEqual(obj.diagnostics.diagnostics, [])

    def test_compile_trefi(self):
        file = self.write_binding(r'\trefi{value}')
        compiler = Compiler(self.root, self.source)
        obj = compiler.compile(file)
        self.assertEqual(obj.diagnostics.diagnostics, [])
        self.assertEqual(len(obj.references), 2)
        self.assertTupleEqual((self.module_name,), obj.references[0].name)
        self.assertTupleEqual((self.module_name, 'value'),
                              obj.references[1].name)

    def test_compile_Trefvs(self):
        file = self.write_text(r'\Trefvs[target]{v}{a}{l}{u}{e}')
        compiler = Compiler(self.root, self.source)
        obj = compiler.compile(file)
        self.assertEqual(obj.diagnostics.diagnostics, [])
        self.assertTupleEqual(('target',), obj.references[0].name)
        self.assertTupleEqual(('target', 'v-a-l-u-e'), obj.references[1].name)

    def test_compile_mTrefiv(self):
        file = self.write_text(
            r'\mTrefiv[target?value]{ignored}{by}{optional}{arguments}')
        compiler = Compiler(self.root, self.source)
        obj = compiler.compile(file)
        self.assertEqual(len(obj.references), 2)
        self.assertTupleEqual(('target',), obj.references[0].name)
        self.assertTupleEqual(('target', 'value'), obj.references[1].name)
        self.assertEqual(len(obj.diagnostics.diagnostics), 1)
        self.assertEqual(
            obj.diagnostics.diagnostics[0].code, DiagnosticCodeName.MTREF_DEPRECATION_CHECK.value)

    def test_compile_atrefiii(self):
        file = self.write_text(
            r'\atrefiii[target]{this value is ignored}{a}{referenced}{value}')
        compiler = Compiler(self.root, self.source)
        obj = compiler.compile(file)
        self.assertEqual(len(obj.references), 2)
        self.assertTupleEqual(('target',), obj.references[0].name)
        self.assertTupleEqual(
            ('target', 'a-referenced-value'), obj.references[1].name)
        self.assertEqual(obj.diagnostics.diagnostics, [])

    def test_compile_modsig(self):
        file = self.write_modsig()
        obj = Compiler(self.root, self.source).compile(file)
        sym, = obj.symbol_table.find((self.module_name,))
        self.assertEqual(sym.name, self.module_name)
        self.assertEqual(len(obj.symbol_table.children), 1)

    def test_compile_symi(self):
        file = self.write_modsig(r'\symi{value}')
        obj = Compiler(self.root, self.source).compile(file)
        sym, = obj.symbol_table.find((self.module_name, 'value'))
        self.assertEqual(sym.name, 'value')
        self.assertListEqual(obj.diagnostics.diagnostics, [])

    def test_compile_symdef(self):
        file = self.write_modsig(r'\symdef{value}')
        obj = Compiler(self.root, self.source).compile(file)
        sym, = obj.symbol_table.find((self.module_name, 'value'))
        self.assertEqual(sym.name, 'value')
        self.assertListEqual(obj.diagnostics.diagnostics, [])

    def test_compile_duplicate_symdef(self):
        file = self.write_modsig(r'''
            \symdef{value}
            \symdef{value}''')
        obj = Compiler(self.root, self.source).compile(file)
        sym1, sym2, = obj.symbol_table.find((self.module_name, 'value'))
        self.assertEqual(sym1.name, 'value')
        self.assertEqual(sym2.name, 'value')
        self.assertListEqual(obj.diagnostics.diagnostics, [])

    def test_compile_vardef(self):
        file = self.write_modsig(r'\vardef{value}')
        obj = Compiler(self.root, self.source).compile(file)
        sym, = obj.symbol_table.find((self.module_name, 'value'))
        self.assertEqual(sym.name, 'value')
        self.assertListEqual(obj.diagnostics.diagnostics, [])

    def test_compile_duplicate_vardef(self):
        file = self.write_modsig(r'''
            \vardef{value}
            \vardef{value}''')
        obj = Compiler(self.root, self.source).compile(file)
        sym1, sym2, = obj.symbol_table.find((self.module_name, 'value'))
        self.assertEqual(sym1.name, 'value')
        self.assertEqual(sym2.name, 'value')
        self.assertListEqual(obj.diagnostics.diagnostics, [])

    def test_compile_symdef_name(self):
        file = self.write_modsig(
            r'\symdef[name=value]{argument will be ignored}')
        obj = Compiler(self.root, self.source).compile(file)
        sym, = obj.symbol_table.find((self.module_name, 'value'))
        self.assertEqual(sym.name, 'value')
        self.assertListEqual(obj.diagnostics.diagnostics, [])

    def test_compile_gimport(self):
        file = self.write_modsig(
            r'\gimport{value}')
        obj = Compiler(self.root, self.source).compile(file)
        dep, = obj.dependencies
        self.assertEqual(dep.file_hint, self.source / 'value.tex')
        self.assertEqual(dep.module_name, 'value')
        ref, = obj.references
        self.assertTupleEqual(ref.name, ('value',))
        self.assertListEqual(obj.diagnostics.diagnostics, [])

    def test_compile_gimport_oarg(self):
        file = self.write_modsig(
            r'\gimport[path/to/repo]{value}')
        obj = Compiler(self.root, self.source).compile(file)
        dep, = obj.dependencies
        self.assertEqual(
            dep.file_hint, self.root / 'path/to/repo/source/value.tex')
        self.assertEqual(dep.module_name, 'value')
        ref, = obj.references
        self.assertTupleEqual(ref.name, ('value',))
        self.assertListEqual(obj.diagnostics.diagnostics, [])

    def test_cant_infer_referenced_module(self):
        file = self.write_text(r'\trefi{value}')
        obj = Compiler(self.root, self.source).compile(file)
        diag, = obj.diagnostics.diagnostics
        self.assertEqual(
            diag.code,
            DiagnosticCodeName.CANT_INFER_REF_MODULE_OUTSIDE_MODULE.value)

    def test_duplicate_symbol(self):
        file = self.write_modsig(
            r'''\symi{value}
            \symi{value}''')
        obj = Compiler(self.root, self.source).compile(file)
        diag, = obj.diagnostics.diagnostics
        self.assertEqual(
            diag.code,
            DiagnosticCodeName.DUPLICATE_SYMBOL.value)

    def test_parser_exception(self):
        file = self.write_binding(r'\trefi{')
        obj = Compiler(self.root, self.source).compile(file)
        diag, = obj.diagnostics.diagnostics
        self.assertEqual(
            diag.code,
            DiagnosticCodeName.PARSER_EXCEPTION.value)

    def test_module_file_mismatch(self):
        file = self.write_text(
            r'''\begin{modsig}{wrong module name}\end{modsig}''')
        obj = Compiler(self.root, self.source).compile(file)
        diag, = obj.diagnostics.diagnostics
        self.assertEqual(
            diag.code,
            DiagnosticCodeName.MODULE_FILE_NAME_MISMATCH.value)

    def test_mtref_deprecation(self):
        file = self.write_binding(
            r'\mtrefi[?value]{deprecated mtrefi}')
        obj = Compiler(self.root, self.source).compile(file)
        diag, = obj.diagnostics.diagnostics
        self.assertEqual(
            diag.code,
            DiagnosticCodeName.MTREF_DEPRECATION_CHECK.value)

    def test_mtref_question_mark(self):
        file = self.write_binding(
            r'\mtrefi{questionmark missing}')
        obj = Compiler(self.root, self.source).compile(file)
        codes = set(diag.code for diag in obj.diagnostics.diagnostics)
        self.assertEqual(len(codes), 2)
        self.assertIn(
            DiagnosticCodeName.MTREF_DEPRECATION_CHECK.value,
            codes)
        self.assertIn(
            DiagnosticCodeName.MTREF_QUESTIONMARK_CHECK.value,
            codes)


class TestIntermediate(TestCase, MockGlossary):
    """ This intermediate test is only for basic "does not crash" tests.
    The in depths tests are transitively covered by the test compiler and linker tests.
    """

    def setUp(self) -> None:
        self.setup()

    def tearDown(self) -> None:
        self.cleanup()

    def test_defi(self):
        file = self.write_binding(r'\defiii[name=my-name]{will}{be}{ignored}')
        parser = IntermediateParser(file).parse()
        root, = parser.roots
        self.assertIsInstance(root, ModnlIntermediateParseTree)
        self.assertEqual(root.name.text, self.module_name)
        self.assertEqual(root.lang.text, 'en')
        defi, = root.children
        self.assertIsInstance(defi, DefiIntermediateParseTree)
        self.assertEqual(defi.name, 'my-name')
        self.assertListEqual(
            list(tok.text for tok in defi.tokens), 'will be ignored'.split())


class TestLinker(TestCase, MockGlossary):
    def setUp(self) -> None:
        self.setup()

    def tearDown(self) -> None:
        self.cleanup()

    def _link_binding(self):
        compiler = Compiler(self.root, self.source)
        module_obj = compiler.compile(self.module)
        binding_obj = compiler.compile(self.binding)
        linker = Linker(self.root)
        linked_binding = linker.link(self.binding, {
            self.binding: binding_obj,
            self.module: module_obj,
        }, compiler)
        return linked_binding

    def test_link(self):
        self.write_modsig(r'\symi{value}')
        self.write_binding(r'''
            Reference symi: \trefi{value}
            Define symi: \defi{value}''')
        linked_binding = self._link_binding()
        self.assertListEqual([], linked_binding.diagnostics.diagnostics)
        module_dep, = linked_binding.dependencies
        self.assertEqual(module_dep.file_hint, self.module)
        self.assertEqual(module_dep.module_name, self.module_name)
        self.assertSetEqual(
            set(linked_binding.related_files), {
                self.binding, self.module})
        binding, = linked_binding.symbol_table.find(self.module_name)
        self.assertIsInstance(binding, BindingSymbol)
        module, = binding.find(self.module_name)
        self.assertIsInstance(module, ModuleSymbol)
        symbol, = module.find('value')
        self.assertIsInstance(symbol, DefSymbol)
        qualified_symbol, = binding.find([self.module_name, 'value'])
        self.assertIsInstance(qualified_symbol, DefSymbol)

    def test_missing_dependency(self):
        self.write_binding(r'''
            Reference symi: \trefi{value}
            Define symi: \defi{value}''')
        compiler = Compiler(self.root, self.source)
        binding_obj = compiler.compile(self.binding)
        linker = Linker(self.root)
        linked_binding = linker.link(self.binding, {
            self.binding: binding_obj,
            # self.module: module_obj, # Do not include module
        }, compiler)
        file_not_found, = linked_binding.diagnostics.diagnostics
        self.assertEqual(
            DiagnosticCodeName.FILE_NOT_FOUND.value, file_not_found.code)
        self.assertIn(str(self.module), file_not_found.message)
