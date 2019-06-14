import unittest
from time import sleep, time

from ..linting.document import Document
from ..linting.linter import Linter
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
        symbol_count = len(symbols)
        self.assertEquals(symbol_count, 5)

    def test_module_gimport_count(self):
        imports = list(self._make_module_document().gimports)
        import_count = len(imports)
        self.assertEquals(import_count, 4)

    def test_binding_compile_success(self):
        document = self._make_binding_document()
        self.assertTrue(document.success, "Binding document failed to parse")
        self.assertTrue(not document.exceptions, "Parsing of binding succeeded with exceptions")
        self.assertIsNotNone(document.binding, "Binding expected to be not None")

    def test_binding_definition(self):
        document = self._make_binding_document()
        self.assertIsNotNone(document.binding, "Binding expected")
        self.assertEqual(str(document.module_identifier), "testdb/all_symbol_types/test_module")
        self.assertEqual(str(document.binding.lang), "lang")

    def test_binding_trefi_count(self):
        trefis = list(self._make_binding_document().trefis)
        trefi_count = len(trefis)
        self.assertEqual(trefi_count, 12)

    def test_binding_defi_count(self):
        defis = list(self._make_binding_document().defis)
        defi_count = len(defis)
        self.assertEqual(defi_count, 10)

    @staticmethod
    def _make_module_document():
        return Document('trefier/test/testdb/all_symbol_types/source/module.tex', False)

    @staticmethod
    def _make_binding_document():
        return Document('trefier/test/testdb/all_symbol_types/source/module.lang.tex', False)


class TestImportGraph(unittest.TestCase):
    def test_open_in_image_viewer(self):
        linter = Linter()
        linter.add_directory('trefier/test/testdb/repo2/source')
        linter.update(use_multiprocessing=False)
        linter.import_graph.open_in_image_viewer('testdb/repo2/module1')


class TestLinter(unittest.TestCase):
    def test_first_update(self):
        linter = Linter()
        linter.add_directory('trefier/test/testdb/repo3/source')
        linter.update(use_multiprocessing=False)
        self.assertTrue(not linter.exceptions)
        self.assertEqual(len(linter.ls), 5)
        self.assertEqual(len(linter.modules), 2)
        self.assertEqual(len([e for el in linter.symbols.values() for e in el]), 3)
        self.assertEqual(len(linter.bindings), 3)
        self.assertEqual(len(linter.trefis), 3)
        self.assertEqual(len(linter.defis), 3)

    def test_remove_all(self):
        linter = Linter()
        linter.add_directory('trefier/test/testdb/repo3/source')
        self.assertEqual(linter.update(use_multiprocessing=False), 5)
        self.assertTrue(not linter.exceptions)
        self.assertEqual(len(linter.ls), 5)
        self.assertEqual(len(linter.modules), 2)
        self.assertEqual(len(linter.symbols), 3)
        self.assertEqual(len(linter.bindings), 3)
        self.assertEqual(len(linter.trefis), 3)
        self.assertEqual(len(linter.defis), 3)
        for file in linter.ls:
            linter._unlink(file)
        self.assertTrue(not linter.exceptions)
        self.assertEqual(len(linter.ls), 0)
        self.assertEqual(len(linter.modules), 0)
        self.assertEqual(len(linter.symbols), 0)
        self.assertEqual(len(linter.bindings), 0)
        self.assertEqual(len(linter.trefis), 0)
        self.assertEqual(len(linter.defis), 0)

    def test_threadsafe_read(self):
        linter = Linter()

        time_a = time()
        linter.lock_reader(1, 'a')
        linter.lock_reader(1, 'b')
        delta_a = time() - time_a

        self.assertAlmostEqual(delta_a, 2, 2)

        f1 = Future(lambda: linter.lock_reader(1, 'c'))
        f1.done(ignore)
        f2 = Future(lambda: linter.lock_reader(1, 'd'))
        f2.done(ignore)
        time_b = time()
        f1.join()
        f2.join()

        # reading is parallel
        self.assertAlmostEqual(time() - time_b, 1, 2)

    def test_threadsafe_write(self):
        linter = Linter()

        time_a = time()
        linter.lock_writer(1, 'a')
        linter.lock_writer(1, 'b')
        delta_a = time() - time_a

        self.assertAlmostEqual(delta_a, 2, 2)

        f1 = Future(lambda: linter.lock_writer(1, 'c'))
        f1.done(ignore)
        f2 = Future(lambda: linter.lock_writer(1, 'd'))
        f2.done(ignore)
        time_b = time()
        f1.join()
        f2.join()

        # writing is not parallel
        self.assertAlmostEqual(time() - time_b, 2, 2)


def ignore(*args, **kwargs):
    pass
