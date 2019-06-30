import unittest
from glob import glob

from trefier.misc.location import *
from trefier.linting.document import Document
from trefier.linting.identifiers import *
from trefier.linting.symbols import *
from trefier.linting.linter import Linter
from trefier.linting.imports import ImportGraph


class LinterDocumentTestCase(unittest.TestCase):
    def test_module_compile_success(self):
        document = self._make_module_document()
        self.assertTrue(document.success, "Module document failed to parse")
        self.assertTrue(not document.exceptions, "Parsing of module succeeded with exceptions")
        self.assertIsNotNone(document.module, "Module expected to be not None")

    def test_module_definition(self):
        document = self._make_module_document()
        self.assertIsNotNone(document.module, "Module expected")
        self.assertEqual(str(document.module_identifier), "testdb/all_symbol_types/module")

    def test_module_symbol_count(self):
        symbols = list(self._make_module_document().symis)
        self.assertEquals(len(symbols), 5)

    def test_module_gimport_count(self):
        imports = list(self._make_module_document().gimports)
        self.assertEquals(len(imports), 4)

    def test_binding_compile_success(self):
        document = self._make_binding_document()
        self.assertTrue(document.success, "Binding document failed to parse")
        self.assertTrue(not document.exceptions, "Parsing of binding succeeded with exceptions")
        self.assertIsNotNone(document.binding, "Binding expected to be not None")

    def test_binding_definition(self):
        document = self._make_binding_document()
        self.assertIsNotNone(document.binding, "Binding expected")
        self.assertEqual(str(document.module_identifier), "testdb/all_symbol_types/module")
        self.assertEqual(str(document.binding.lang), "lang")

    def test_binding_trefi_count(self):
        trefis = list(self._make_binding_document().trefis)
        self.assertEqual(len(trefis), 12)

    def test_binding_defi_count(self):
        defis = list(self._make_binding_document().defis)
        self.assertEqual(len(defis), 10)

    @staticmethod
    def _make_module_document():
        return Document('testdb/all_symbol_types/source/module.tex')

    @staticmethod
    def _make_binding_document():
        return Document('testdb/all_symbol_types/source/module.lang.tex')


class TestImportGraph(unittest.TestCase):
    def test_unresolved(self):
        documents = [
            Document('testdb/simple/source/module1.tex'),
            Document('testdb/simple/source/module2.tex'),
        ]
        graph = ImportGraph()
        for d in documents:
            self.assertTrue(d.success)
            self.assertTrue(not d.exceptions)
            graph.add(d)
        self.assertIn('testdb/simple/module3', graph.unresolved)
        self.assertIn('testdb/simple/module1', graph.unresolved['testdb/simple/module3'])
        graph.add(Document('testdb/simple/source/module3.tex'))
        self.assertNotIn('testdb/simple/module3', graph.unresolved)
        self.assertDictEqual(graph.unresolved, {})

    def test_remove_all(self):
        documents = [
            Document('testdb/simple/source/module1.tex'),
            Document('testdb/simple/source/module2.tex'),
        ]
        graph = ImportGraph()
        for d in documents:
            self.assertTrue(d.success)
            self.assertTrue(not d.exceptions)
            graph.add(d)
        graph.update()
        self.assertNotEqual({}, graph.modules)
        self.assertNotEqual({}, graph.graph)
        self.assertNotEqual({}, graph.duplicates)
        self.assertNotEqual({}, graph.references)
        self.assertNotEqual({}, graph.unresolved)
        self.assertNotEqual({}, graph.transitive)
        self.assertNotEqual({}, graph.redundant)
        self.assertNotEqual({}, graph.cycles)
        for d in documents:
            graph.remove(d.module_identifier)
        graph.update()
        self.assertDictEqual({}, graph.modules)
        self.assertDictEqual({}, graph.graph)
        self.assertDictEqual({}, graph.duplicates)
        self.assertDictEqual({}, graph.references)
        self.assertDictEqual({}, graph.unresolved)
        self.assertDictEqual({}, graph.transitive)
        self.assertDictEqual({}, graph.redundant)
        self.assertDictEqual({}, graph.cycles)

    def test_transitive(self):
        documents = list(map(Document, glob('testdb/two_peaks/source/*.tex')))
        graph = ImportGraph()
        for d in documents:
            self.assertTrue(d.success)
            self.assertTrue(not d.exceptions)
            if d.module:
                graph.add(d)
        graph.update()
        self.assertSetEqual(
            {
                'testdb/two_peaks/bottom1',
                'testdb/two_peaks/bottom2',
                'testdb/two_peaks/bottom3'},
            set(graph.transitive['testdb/two_peaks/peak1']))

    def test_reachable(self):
        documents = list(map(Document, glob('testdb/two_peaks/source/*.tex')))
        graph = ImportGraph()
        for d in documents:
            self.assertTrue(d.success)
            self.assertTrue(not d.exceptions)
            if d.module:
                graph.add(d)
        graph.update()
        self.assertSetEqual({
            'testdb/two_peaks/peak1',
            'testdb/two_peaks/middle1',
            'testdb/two_peaks/middle2',
            'testdb/two_peaks/bottom1',
            'testdb/two_peaks/bottom2',
            'testdb/two_peaks/bottom3',
        }, graph.reachable_modules_of('testdb/two_peaks/peak1'))
        self.assertSetEqual({
            'testdb/two_peaks/middle2',
            'testdb/two_peaks/bottom1',
            'testdb/two_peaks/bottom2',
            'testdb/two_peaks/bottom3',
        }, graph.reachable_modules_of('testdb/two_peaks/middle2'))
        self.assertSetEqual({'testdb/two_peaks/bottom1'}, graph.reachable_modules_of('testdb/two_peaks/bottom1'))

    def test_references(self):
        documents = list(map(Document, glob('testdb/two_peaks/source/*.tex')))
        graph = ImportGraph()
        for d in documents:
            self.assertTrue(d.success)
            self.assertTrue(not d.exceptions)
            if d.module:
                graph.add(d)
        graph.update()
        self.assertSetEqual({
            'testdb/two_peaks/middle1',
            'testdb/two_peaks/middle2',
            'testdb/two_peaks/middle3',
        }, set(graph.references['testdb/two_peaks/bottom1']))

    def test_cycles(self):
        documents = list(map(Document, glob('testdb/cycle/source/*.tex')))
        graph = ImportGraph()
        for d in documents:
            self.assertTrue(d.success, msg=d.file)
            self.assertListEqual([], d.exceptions, msg=d.file)
            if d.module:
                graph.add(d)
        graph.update()
        self.assertDictEqual({}, graph.unresolved)
        self.assertSetEqual({
            'testdb/cycle/module3',
            'testdb/cycle/module4',
            'testdb/cycle/module5',
            'testdb/cycle/self_cycle',
        }, set(module for module, items in graph.cycles.items() if items))

    def test_redundant_transitive(self):
        documents = list(map(Document, glob('testdb/redundant/source/*.tex')))
        graph = ImportGraph()
        for d in documents:
            self.assertTrue(d.success, msg=d.file)
            self.assertListEqual([], d.exceptions, msg=d.file)
            if d.module:
                graph.add(d)
        graph.update()
        self.assertSetEqual(
            {'testdb/redundant/module4',
             'testdb/redundant/module5',
             'testdb/redundant/module6',
             'testdb/redundant/module7'},
            set(graph.transitive['testdb/redundant/module1'])
        )
        self.assertDictEqual({}, graph.unresolved)
        self.assertSetEqual(
            {'testdb/redundant/module4'},
            set([module for module, items in graph.redundant.items() if items])
        )

        for d in documents:
            if 'module5' in d.file and d.module:
                graph.remove(d.module_identifier)
        graph.update()
        self.assertNotIn('testdb/redundant/module6', graph.unresolved)
        self.assertIn('testdb/redundant/module5', graph.unresolved)
        self.assertNotIn('testdb/redundant/module5', graph.references)
        self.assertIn('testdb/redundant/module6', graph.references)
        self.assertNotIn('testdb/redundant/module5', graph.graph)
        self.assertNotIn('testdb/redundant/module5', graph.cycles)
        self.assertNotIn('testdb/redundant/module5', graph.transitive)
        self.assertSetEqual(
            {'testdb/redundant/module4', 'testdb/redundant/module5', 'testdb/redundant/module7'},
            set(graph.transitive['testdb/redundant/module1'])
        )


class TestLinter(unittest.TestCase):
    def test_first_update(self):
        linter = Linter()
        linter.add('testdb/repo3/source')
        linter.update(use_multiprocessing=False)
        self.assertEqual(5, len(linter.ls()))
        self.assertEqual(2, len(linter.modules()))
        self.assertEqual(3, len(linter.symbols()))
        self.assertEqual(3, len(linter.bindings()))
        self.assertEqual(3, len(linter.trefis()))
        self.assertEqual(5, len(linter.defis()))

    def test_unlink_all(self):
        linter = Linter()
        linter.add('testdb/repo3/source')
        linter.update(use_multiprocessing=False)
        self.assertEqual(5, len(linter.ls()))
        self.assertEqual(2, len(linter.modules()))
        self.assertEqual(3, len(linter.symbols()))
        self.assertEqual(3, len(linter.bindings()))
        self.assertEqual(3, len(linter.trefis()))
        self.assertEqual(5, len(linter.defis()))
        for file in linter.ls():
            linter._unlink(file)
        linter.import_graph.update()
        self.assertListEqual([], linter.ls())
        self.assertListEqual([], linter.modules())
        self.assertListEqual([], linter.symbols())
        self.assertListEqual([], linter.bindings())
        self.assertListEqual([], linter.trefis())
        self.assertListEqual([], linter.defis())
        self.assertDictEqual({}, linter._map_file_to_document)
        self.assertDictEqual({}, linter._map_module_identifier_to_bindings)
        self.assertDictEqual({}, linter._map_module_identifier_to_module)

    def test_link_unlink(self):
        file = 'testdb/all_symbol_types/source/module.tex'
        document = Document(file)
        self.assertTrue(document.success)
        linter = Linter()
        self.assertFalse(linter._is_linked(file))
        linter._link(document)
        linter.import_graph.update()
        self.assertTrue(linter._is_linked(file))
        linter._unlink(file)
        linter.import_graph.update()
        self.assertFalse(linter._is_linked(file))
        linter._link(document)
        linter.import_graph.update()
        self.assertTrue(linter._is_linked(file))

    def test_symbol_parsing(self):
        linter = self._setup()

        file = '/home/marian/projects/trefier-backend/trefier/tests/testdb/two_peaks/source/bottom1.lang.tex'
        doc = linter._map_file_to_document[file]
        self.assertEqual(2, len(doc.trefis))
        self.assertEqual(2, len(doc.defis))
        trefi = doc.trefis[-1]
        self.assertEqual('bottom1-symdef1', trefi.symbol_name)
        self.assertEqual(2, len(trefi.symbol_name_locations))
        self.assertIsNone(trefi.target_module_location)
        self.assertFalse(trefi.is_alt)
        self.assertEqual(1, len(doc.defis[0].symbol_name_locations))
        self.assertEqual('bottom1-symbol1', doc.defis[0].symbol_name)
        self.assertIsNone(doc.defis[0].name_argument_location)
        defi = doc.defis[-1]
        self.assertEqual('bottom1-symdef1', defi.symbol_name)
        self.assertEqual(3, len(defi.symbol_name_locations))
        self.assertEqual(33, defi.symbol_name_locations[0].range.begin.column)
        self.assertEqual(50, defi.symbol_name_locations[1].range.begin.column)
        self.assertEqual(55, defi.symbol_name_locations[2].range.begin.column)
        self.assertTrue(defi.is_alt)
        self.assertIsNotNone(defi.name_argument_location)

        file = '/home/marian/projects/trefier-backend/trefier/tests/testdb/two_peaks/source/bottom1.tex'
        doc = linter._map_file_to_document[file]
        self.assertEqual(2, len(doc.symis))
        self.assertEqual('symii', doc.symis[0].env_name)
        self.assertEqual('bottom1-symbol1', doc.symis[0].symbol_name)
        self.assertEqual(1, len(doc.symis[0].symbol_name_locations))
        self.assertEqual('symdef', doc.symis[1].env_name)
        self.assertEqual('bottom1-symdef1', doc.symis[1].symbol_name)
        self.assertEqual(1, len(doc.symis[1].symbol_name_locations))
        self.assertEqual(18, doc.symis[1].symbol_name_locations[0].range.begin.column)
        self.assertEqual(33, doc.symis[1].symbol_name_locations[0].range.end.column)

    def test_goto_definition(self):
        linter = self._setup()
        self.assertRaises(Exception, lambda: linter.goto_definition('', 1, 2))
        file = '/home/marian/projects/trefier-backend/trefier/tests/testdb/two_peaks/source/peak1.lang.tex'

        self.assertIsNone(linter.goto_definition(file, 1, 33))
        self.assertIsNone(linter.goto_definition(file, 1, 40))
        binding_module = linter.goto_definition(file, 1, 34)
        self.assertIsNotNone(binding_module)
        self.assertIsInstance(binding_module, ModuleDefinitonSymbol)
        self.assertEqual(binding_module, linter.goto_definition(file, 1, 39))
        self.assertEqual('peak1', binding_module.module_name)

        trefi_definition = linter.goto_definition(file, 2, 20)
        self.assertIsNotNone(trefi_definition)
        self.assertIsInstance(trefi_definition, SymiSymbol)
        self.assertEqual('peak1-symbol1', trefi_definition.symbol_name)

        defi_definition = linter.goto_definition(file, 3, 35)
        self.assertIsNotNone(defi_definition)
        self.assertIsInstance(defi_definition, SymiSymbol)
        self.assertEqual('peak1-symbol1', defi_definition.symbol_name)

        trefi_module_definition = linter.goto_definition(file, 4, 26)
        self.assertIsNotNone(trefi_module_definition)
        self.assertIsInstance(trefi_module_definition, ModuleDefinitonSymbol)
        self.assertEqual('middle1', trefi_module_definition.module_name)

        trefi_module_defi_definition = linter.goto_definition(file, 4, 36)
        self.assertIsNotNone(trefi_module_defi_definition)
        self.assertIsInstance(trefi_module_defi_definition, SymiSymbol)
        self.assertEqual('testdb/two_peaks/middle1', str(trefi_module_defi_definition.module))
        self.assertEqual('middle1-symbol1', trefi_module_defi_definition.symbol_name)

        self.assertIsNone(linter.goto_definition(file, 8, 29))
        trefi_module_arg = linter.goto_definition(file, 8, 35)
        self.assertIsNotNone(trefi_module_arg)
        self.assertIsInstance(trefi_module_arg, ModuleDefinitonSymbol)
        self.assertEqual('testdb/two_peaks/bottom1', str(trefi_module_arg.module))
        self.assertEqual(trefi_module_arg, linter.goto_definition(file, 8, 37))

        self.assertIsNone(linter.goto_definition(file, 8, 54))
        trefi_symbol_arg = linter.goto_definition(file, 8, 40)
        self.assertIsNotNone(trefi_symbol_arg)
        self.assertIsInstance(trefi_symbol_arg, SymiSymbol)
        self.assertEqual(trefi_symbol_arg, linter.goto_definition(file, 8, 38))
        self.assertEqual('symdef', trefi_symbol_arg.env_name)
        self.assertEqual('bottom1-symdef1', trefi_symbol_arg.symbol_name)

        module_file = '/home/marian/projects/trefier-backend/trefier/tests/testdb/two_peaks/source/peak1.tex'

        module_definition = linter.goto_definition(module_file, 1, 35)
        self.assertIsNotNone(module_definition)
        self.assertIsInstance(module_definition, ModuleDefinitonSymbol)
        self.assertEqual('testdb/two_peaks/peak1', str(module_definition.module))

        gimport_module = linter.goto_definition(module_file, 2, 15)
        self.assertIsNotNone(gimport_module)
        self.assertIsInstance(gimport_module, ModuleDefinitonSymbol)
        self.assertEqual('testdb/two_peaks/middle1', str(gimport_module.module))

        symii = linter.goto_definition(module_file, 4, 16)
        self.assertIsNotNone(symii)
        self.assertIsInstance(symii, SymiSymbol)
        self.assertEqual('symii', symii.env_name)
        self.assertEqual('testdb/two_peaks/peak1', str(symii.module))
        self.assertEqual('peak1-symbol1', symii.symbol_name)

        symdef_module_file = ('/home/marian/projects/trefier-backend/trefier/tests/'
                              'testdb/two_peaks/source/bottom1.tex')
        self.assertIsNone(linter.goto_definition(symdef_module_file, 3, 17))
        self.assertIsNone(linter.goto_definition(symdef_module_file, 3, 34))
        symdef_symbol = linter.goto_definition(symdef_module_file, 3, 18)
        self.assertIsNotNone(symdef_symbol)
        self.assertIsInstance(symdef_symbol, SymiSymbol)
        self.assertEqual(1, len(symdef_symbol.symbol_name_locations))

        symdef_name_binding = ('/home/marian/projects/trefier-backend/trefier/tests/'
                               'testdb/two_peaks/source/bottom1.lang.tex')
        self.assertIsNone(linter.goto_definition(symdef_name_binding, 4, 32))
        self.assertIsNone(linter.goto_definition(symdef_name_binding, 4, 49))
        symdef_symbol = linter.goto_definition(symdef_name_binding, 4, 33)
        self.assertIsNotNone(symdef_symbol)
        self.assertIsInstance(symdef_symbol, SymiSymbol)
        self.assertEqual(symdef_symbol, linter.goto_definition(symdef_name_binding, 4, 48))

    def test_goto_implementation(self):
        linter = self._setup()

        file = '/home/marian/projects/trefier-backend/trefier/tests/testdb/two_peaks/source/bottom1.lang.tex'

        impl = linter.goto_implementation(file, 5, 40)
        self.assertEqual(2, len(impl))
        for name_arg_impl in impl:
            self.assertIsInstance(name_arg_impl, DefiSymbol)
            self.assertEqual('testdb/two_peaks/bottom1', str(name_arg_impl.module))
            self.assertEqual('bottom1-symdef1', name_arg_impl.symbol_name)
            self.assertIsNotNone(name_arg_impl.name_argument_location)

        file = '/home/marian/projects/trefier-backend/trefier/tests/testdb/two_peaks/source/peak2.lang.tex'
        impl = linter.goto_implementation(file, 6, 40)
        self.assertEqual(1, len(impl))
        for trefi_impl in impl:
            self.assertIsInstance(trefi_impl, DefiSymbol)
            self.assertEqual('middle3-symbol1', trefi_impl.symbol_name)

        impl = linter.goto_implementation(file, 6, 20)
        self.assertEqual(1, len(impl))
        for trefi_module_impl in impl:
            self.assertIsInstance(trefi_module_impl, ModuleBindingDefinitionSymbol)
            self.assertEqual('testdb/two_peaks/middle3', str(trefi_module_impl.module))

    def test_find_references(self):
        linter = self._setup()
        file = '/home/marian/projects/trefier-backend/trefier/tests/testdb/two_peaks/source/bottom3.lang.tex'
        ref_module = linter.find_references(file, 1, 36)
        self.assertEqual(1, len(ref_module))

        file = '/home/marian/projects/trefier-backend/trefier/tests/testdb/two_peaks/source/peak1.lang.tex'
        refs = linter.find_references(file, 8, 60)
        self.assertEqual(5, len(refs))

    def test_unresolved_missing_import(self):
        linter = Linter()
        linter.add('testdb/missing_import/source')
        linter.update(use_multiprocessing=False)
        raise NotImplementedError()

    def test_name_missing(self):
        linter = Linter()
        linter.add('testdb/name_missing/source')
        linter.update(use_multiprocessing=False)

    def _setup(self):
        linter = Linter()
        linter.add('testdb/two_peaks/source')
        linter.update(use_multiprocessing=False)
        return linter

    def test_custom_update(self):
        linter = self._setup()
        linter.update(use_multiprocessing=False)
