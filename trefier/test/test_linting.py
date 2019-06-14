import unittest
from time import sleep, time

from trefier.linting.document import Document
from trefier.linting.linter import Linter
from trefier.linting.imports import ImportGraph
from trefier.misc.future import Future


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
        return Document('trefier/test/testdb/all_symbol_types/source/module.tex')

    @staticmethod
    def _make_binding_document():
        return Document('trefier/test/testdb/all_symbol_types/source/module.lang.tex')


class TestImportGraph(unittest.TestCase):
    def _setup(self):
        linter = Linter()
        linter.add_directory('trefier/test/testdb/simple/source')
        self.assertEqual(3, linter.update(use_multiprocessing=False))
        self.assertTrue(not linter.exceptions)
        return linter

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
        self.assertDictEqual({}, graph.modules)
        self.assertDictEqual({}, graph.graph)
        self.assertDictEqual({}, graph.duplicates)
        self.assertDictEqual({}, graph.references)
        self.assertDictEqual({}, graph.unresolved)
        self.assertDictEqual({}, graph.transitive)
        self.assertDictEqual({}, graph.redundant)
        self.assertDictEqual({}, graph.cycles)

    def test_open_in_image_viewer(self):
        linter = self._setup()
        linter.import_graph.open_in_image_viewer('testdb/simple/module1')


class TestLinter(unittest.TestCase):
    def test_first_update(self):
        linter = Linter()
        linter.add_directory('trefier/test/testdb/repo3/source')
        linter.update(use_multiprocessing=False)
        self.assertTrue(not linter.exceptions)
        self.assertEqual(5, len(linter.ls))
        self.assertEqual(2, len(linter.modules))
        self.assertEqual(3, len(linter.symbols))
        self.assertEqual(3, len(linter.bindings))
        self.assertEqual(3, len(linter.trefis))
        self.assertEqual(3, len(linter.defis))

    def test_unlink_all(self):
        linter = Linter()
        linter.add_directory('testdb/repo3/source')
        self.assertEqual(5, linter.update(use_multiprocessing=False))
        self.assertTrue(not linter.exceptions)
        self.assertEqual(5, len(linter.ls))
        self.assertEqual(2, len(linter.modules))
        self.assertEqual(3, len(linter.symbols))
        self.assertEqual(3, len(linter.bindings))
        self.assertEqual(3, len(linter.trefis))
        self.assertEqual(3, len(linter.defis))
        for file in linter.ls:
            linter._unlink(file)
        self.assertTrue(not linter.exceptions)
        self.assertListEqual([], linter.ls)
        self.assertListEqual([], linter.modules)
        self.assertListEqual([], linter.symbols)
        self.assertListEqual([], linter.bindings)
        self.assertDictEqual({}, linter.trefis)
        self.assertDictEqual({}, linter.defis)
        self.assertDictEqual({}, linter._map_file_to_document)
        self.assertDictEqual({}, linter._map_module_identifier_to_bindings)
        self.assertDictEqual({}, linter._map_module_identifier_to_module)
        self.assertDictEqual({}, linter.failed_to_parse)
        self.assertDictEqual({}, linter.exceptions)

    def test_link_unlink(self):
        file = 'trefier/test/testdb/all_symbol_types/source/module.tex'
        document = Document(file)
        self.assertTrue(document.success)
        linter = Linter()
        self.assertFalse(linter._is_linked(file))
        linter._link(document)
        self.assertTrue(linter._is_linked(file))
        linter._unlink(file)
        self.assertFalse(linter._is_linked(file))
        linter._link(document)
        self.assertTrue(linter._is_linked(file))

    def test_symbol_positions(self):
        linter = Linter()
        linter.add_directory('trefier/test/testdb/two_peaks/source')
        self.assertEqual(linter.update(use_multiprocessing=False), 16)
        self.assertTrue(not linter.exceptions)

    class TestThreadsafeLinter(Linter):
        def lock_reader(self, delay):
            from time import sleep
            with self._rwlock.reader():
                sleep(delay)

        def lock_writer(self, delay):
            from time import sleep
            with self._rwlock.writer():
                sleep(delay)

    def test_threadsafe_read(self):
        linter = TestLinter.TestThreadsafeLinter()

        time_a = time()
        linter.lock_reader(1)
        linter.lock_reader(1)
        delta_a = time() - time_a

        self.assertAlmostEqual(2, delta_a, 2)

        f1 = Future(lambda: linter.lock_reader(1)).done(ignore)
        f2 = Future(lambda: linter.lock_reader(1)).done(ignore)

        time_b = time()

        f1.join()
        f2.join()

        # reading is parallel
        self.assertAlmostEqual(1, time() - time_b, 2)

    def test_threadsafe_write(self):
        linter = TestLinter.TestThreadsafeLinter()

        time_a = time()
        linter.lock_writer(1)
        linter.lock_writer(1)
        delta_a = time() - time_a

        self.assertAlmostEqual(2, delta_a, 2)

        f1 = Future(lambda: linter.lock_writer(1)).done(ignore)
        f2 = Future(lambda: linter.lock_writer(1)).done(ignore)

        time_b = time()
        f1.join()
        f2.join()

        # writing is not parallel
        self.assertAlmostEqual(2, time() - time_b, 2)


def ignore(*args, **kwargs):
    pass
