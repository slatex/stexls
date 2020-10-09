from stexls.stex.compiler import ObjectfileNotFoundError
from typing import Callable, Iterable, Dict, Optional, List
from pathlib import Path
from multiprocessing import Pool
from stexls.vscode import DiagnosticSeverity, Location
from stexls.stex import *
from stexls.util.workspace import Workspace
import logging

log = logging.getLogger(__name__)

__all__ = ['LintingResult', 'Linter']

class LintingResult:
    def __init__(self, obj: StexObject):
        self.object = obj

    def format_messages(self, format_string: str = '{relative_file}:{line}:{column} {severity} - {message} ({code})', diagnosticlevel: DiagnosticSeverity = DiagnosticSeverity.Information):
        """ Prints all errors according to the provided @format_string and @diagnosticlevel.

        Parameters:
            format_string: A str.format format. Available variables are uri, file, filename, relative_file, line, column, code, severity and message.
            diagnosticlevel: The max severity level printet.
        """
        file = self.object.file
        filename = file.name
        uri = file.as_uri()
        try:
            relative_file = file.relative_to(Path.cwd())
        except:
            relative_file = file
        for diagnostic in self.object.diagnostics:
            if diagnostic.severity.value > diagnosticlevel.value:
                continue
            line = diagnostic.range.start.line + 1
            column = diagnostic.range.start.character + 1
            msg = format_string.format(
                uri=uri,
                file=file,
                filename=filename,
                relative_file=relative_file,
                line=line,
                column=column,
                severity=diagnostic.severity.name,
                code=diagnostic.code,
                message=diagnostic.message)
            print(msg)

    def format_parseable(self):
        pass


class Linter:
    def __init__(self,
        workspace: Workspace,
        outdir: Path = None,
        enable_global_validation: bool = False,
        num_jobs: int = 1,
        on_progress_fun: Callable[[Iterable, Optional[str], Optional[List[str]]], Iterable] = None):
        """ Initializes a linter object.

        Parameters:
            workspace: Workspace this linter works on.
            outdir: Output directory to where the compiler will store it's output at.
            enable_global_validation: If enabled, will compile the whole workspace and use all symbols for validation purposes.
            num_jobs: Number of processes to use for compilation.
            on_progress_fun: Function that creates a new iterable from a give input iterable, enabling progress tracking.
                Arguments of the progress function are the input iterator, a string with information about
                what the input iterable is used for and an optional list of strings with information each element
                of the input iterable.
        """
        self.workspace = workspace
        self.outdir = outdir or (Path.cwd() / 'objects')
        self.enable_global_validation = enable_global_validation
        self.num_jobs = num_jobs
        self.on_progress_fun = on_progress_fun
        self.compiler = Compiler(self.workspace.root, self.outdir)
        self.linker = Linker(self.outdir)
        # The objectbuffer stores all compiled objects
        self._object_buffer: Dict[Path, StexObject] = dict()
        # THe linked object buffer bufferes all linked objects
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
        try:
            return self.compiler.load_from_objectfile(file)
        except ObjectfileNotFoundError:
            return None

    def _compile_workspace(self):
        ' Compiles or loads all files in the workspace and bufferes them in ram. '
        with Pool(self.num_jobs) as pool:
            files = list(self.workspace.files)
            if self.num_jobs <= 1:
                it = map(self._compile_file_with_respect_to_workspace, files)
            else:
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
