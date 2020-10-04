from typing import Callable, Iterable, Dict, Optional, List
from pathlib import Path
import functools
from multiprocessing import Pool
from stexls.vscode import Location
from stexls.stex import *
from stexls.util.workspace import Workspace
import logging

log = logging.getLogger(__name__)

__all__ = ['LintingResult', 'Linter']

class LintingResult:
    def __init__(self, obj: StexObject):
        self.object = obj

    def format_messages(self):
        for range, errors in self.object.errors.items():
            loc = Location(self.object.file.as_uri(), range)
            for err in errors:
                print(loc.format_link(), err)

    def format_parseable(self):
        pass


class Linter:
    def __init__(self,
        workspace: Workspace,
        outdir: Path = None,
        format_parseable: bool = False,
        enable_global_validation: bool = False,
        num_jobs: int = 1,
        on_progress_fun: Callable[[Iterable, Optional[str], Optional[List[str]]], Iterable] = None):
        self.workspace = workspace
        self.outdir = outdir or (Path.cwd() / 'objects')
        self.format_parsable = format_parseable
        self.enable_global_validation = enable_global_validation
        self.num_jobs = num_jobs
        self.on_progress_fun = on_progress_fun
        self.compiler = Compiler(self.workspace.root, self.outdir)
        self.linker = Linker(self.outdir)
        self._object_buffer: Dict[Path, StexObject] = dict()
        self._linked_object_buffer: Dict[Path, StexObject] = dict()
        if self.enable_global_validation:
            self._compile_workspace()

    def _compile_file_with_respect_to_workspace(self, file: Path) -> Optional[StexObject]:
        ' Compiles or loads the file using external information from the linter\'s workspace member. '
        if self.compiler.recompilation_required(file, self.workspace.get_time_live_modified(file)):
            content = self.workspace.read_file(file) if self.workspace.is_open(file) else None
            try:
                return self.compiler.compile(file, content=content)
            except FileNotFoundError:
                return None
        buffered = self._object_buffer.get(file)
        objectfile = self.compiler.get_objectfile_path(file)
        if buffered and objectfile.is_file() and objectfile.lstat().st_mtime < buffered.creation_time:
            return buffered
        return self.compiler.load_from_objectfile(file)

    def _compile_workspace(self):
        ' Compiles or loads all files in the workspace and bufferes them in ram. '
        with Pool(self.num_jobs) as pool:
            files = list(self.workspace.files)
            it = pool.imap(self._compile_file_with_respect_to_workspace, files)
            if self.on_progress_fun:
                it = self.on_progress_fun(it, 'Loading Workspace', files)
            self._object_buffer.update(dict(zip(files, it)))

    def compile_related(self, file: Path) -> Dict[Path, StexObject]:
        ' Compiles all dependencies of the file, the file itself and updates the buffer. The dict with compiled files is returned. '
        queue = [file]
        visited = {}
        while queue:
            file = queue.pop()
            if file in visited:
                continue
            obj = self._compile_file_with_respect_to_workspace(file)
            visited[file] = obj
            self._object_buffer[file] = obj
            for dep in obj.dependencies:
                if dep.file_hint in queue:
                    continue
                queue.append(dep.file_hint)
        return visited

    def lint(self, file: Path) -> LintingResult:
        objects = self.compile_related(file)
        ln = self.linker.link(file, objects)
        more_objects = self._object_buffer if self.enable_global_validation else {}
        self.linker.validate_object_references(ln, more_objects=more_objects)
        return LintingResult(ln)
