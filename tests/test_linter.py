from unittest import TestCase

from stexls.linter.linter import Linter
from stexls.util.workspace import Workspace

from tests.mock import MockGlossary


class TestLinter(TestCase, MockGlossary):
    def setUp(self):
        self.setup()
        self.workspace = Workspace(self.root)
        self.linter = Linter(
            self.workspace,
            outdir=self.root,
            enable_global_validation=True)

    def tearDown(self) -> None:
        self.cleanup()

    def test_lint(self):
        self.write_modsig(r'''\symi{value}\symii{error}''')
        self.write_binding(r'''
            \trefi{does not exist}
            \trefi{value}
            \drefii{drefi}{fails}
        ''')
        objects = list(self.linter.compile_workspace())
        dependencies = self.linter.find_dependent_files_of(self.module)
        self.assertSetEqual({self.binding, self.module}, dependencies)
        module_lint = self.linter.lint(self.module)
        binding_lint = self.linter.lint(self.binding)
        raise NotImplementedError
