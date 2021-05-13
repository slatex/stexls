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

    def test_ok_smglom(self):
        module = self.module_name
        self.write_modsig(r'''
            \symi{symbol1}
            \symii{symbol}{2}
            \symdef{symdef}
        ''')
        self.write_binding(r'''
            \trefi{symbol1}
            \trefii{symbol}{2}
            \adefii{symdef}{defines}{symdef}
        ''')
        self.new_module('module2')
        self.write_modsig(rf'''
            \gimport{{{module}}}
            \symiv{{symbol}}{{in}}{{new}}{{module}}
            \symdef[noverb]{{does-not-have-a-trefi}}
        ''')
        self.write_binding(rf'''
            \trefi[{module}]{{symbol1}}
            \trefii[{module}]{{symbol}}{{2}}
            \trefi{{symdef}}
            \defi[name=symbol-in-new-module]{{define using 'name' argument}}
            \atrefi{{symbol-in-new-module}}{{trefi by using the name with '-' directly in 'a' rarg}}
        ''')
        compile_iter = self.linter.compile_workspace()
        compiled_file_paths = list(compile_iter)
        for file in compiled_file_paths:
            result = self.linter.lint(file)
            self.assertListEqual([], result.diagnostics)

    def test_lint(self):
        self.write_modsig(r'''\symi{value}\symii{error}''')
        self.write_binding(r'''
            \trefi{does not exist}
            \trefi{value}
            \drefii{drefi}{fails}
        ''')
        objects = list(self.linter.compile_workspace())
        dependencies = self.linter.find_users_of_file(self.module)
        self.assertSetEqual({self.binding, self.module}, dependencies)
        module_lint = self.linter.lint(self.module)
        binding_lint = self.linter.lint(self.binding)
        raise NotImplementedError

    def test_lint_gview(self):
        file = self.write_text(r'''
            \begin{gviewnl}[creators=miko,fromrepos=smglom/algebra]{semilattice-algord}{en}
                {semi-lattice}{meetjoin-semilattice}

                Any \trefi[semi-lattice]{semi-lattice} $\mvstructure{\magmaset,\magmaopOp}$ induces a
                \trefii[partial-order]{partial}{ordering} $\fundefequiv{x,y}{\pole{x}y}{\eq{x,\magmaop{x}y}}$
                for which \trefi[supinf?supremum]{suprema} and \trefi[supinf?infimum]{infima} exist.
            \end{gviewnl}l
        ''')
        result = self.linter.lint(file)
        print(result)
        raise NotImplementedError
