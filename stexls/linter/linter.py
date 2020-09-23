from typing import Callable, Iterable
from pathlib import Path
from multiprocessing import Pool
from stexls.vscode import Location
from stexls.stex import *
from stexls.util.workspace import Workspace


class Linter:
    def __init__(
        self,
        workspace: Workspace,
        outdir: Path = None,
        format_parseable: bool = False,
        enable_global_reference_counting: bool = False,
        enable_global_name_suggestions: bool = False,
        num_jobs: int = 1,
        on_progress_fun: Callable[[Iterable, int], None] = None):
        self.workspace = workspace
        self.outdir = outdir or (Path.cwd() / 'objects')
        self.format_parsable = format_parseable
        self.enable_global_reference_counting = enable_global_reference_counting
        self.enable_global_name_suggestions = enable_global_name_suggestions
        self._global_step = enable_global_name_suggestions or enable_global_reference_counting
        self.num_jobs = num_jobs
        self.on_progress_fun = on_progress_fun
        self.compiler = Compiler(workspace, self.outdir)
        self.linker = Linker(workspace, self.outdir)

    def compile_related(self, file: Path):
        o = self.compiler.compile(file)
        for dep in o.dependencies:
            if self.compiler.recompilation_required(dep.file_hint):
                self.compile_related(dep.file_hint)

    def compile_workspace(self):
        files = list(filter(self.compiler.recompilation_required, self.workspace.files))
        if not files: return
        with Pool(self.num_jobs) as pool:
            if self.on_progress_fun:
                self.on_progress_fun(pool.imap(self.compiler.compile, files), len(files))
            else:
                pool.map(self.compiler.compile, files)

    def lint(self, file: Path) -> int:
        if self._global_step:
            self.compile_workspace()
        else:
            self.compile_related(file)
        ln = self.linker.link(file)
        if self.format_parsable:
            self._format_parseable(ln)
        else:
            self._format_messages(ln)
        return len(ln.errors)

    def _format_messages(self, obj: StexObject):
        for range, errors in obj.errors.items():
            loc = Location(obj.file.as_uri(), range)
            for err in errors:
                print(loc.format_link(relative=True, relative_to=self.workspace.root), err)

    def _format_parseable(self, obj: StexObject):
        # TODO: Parseable format
        pass
