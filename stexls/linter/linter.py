from stexls.stex.compiler import ObjectfileNotFoundError
from typing import Callable, Iterable, Dict, Iterator, Optional, List, Set
from pathlib import Path
from multiprocessing import Pool
from stexls.vscode import *
from stexls.stex import *
from stexls.util.workspace import Workspace
import logging

log = logging.getLogger(__name__)

__all__ = ['LintingResult', 'Linter']

class LintingResult:
    def __init__(self, obj: StexObject):
        self.object = obj

    @property
    def uri(self) -> str:
        return self.object.file.as_uri()

    @property
    def diagnostics(self) -> List[Diagnostic]:
        return self.object.diagnostics.diagnostics

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
        num_jobs: int = 1):
        """ Initializes a linter object.

        Parameters:
            workspace: Workspace this linter works on.
            outdir: Output directory to where the compiler will store it's output at.
            enable_global_validation: If enabled, will look at every cached compiled file in order to create better
                diagnostics related to references and other things.
            num_jobs: Number of processes to use for compilation.
        """
        self.workspace = workspace
        self.outdir = outdir or (Path.cwd() / 'objects')
        self.enable_global_validation = enable_global_validation
        self.num_jobs = num_jobs
        self.compiler = Compiler(self.workspace.root, self.outdir)
        self.linker = Linker(self.outdir)
        # The objectbuffer stores all compiled objects
        self._object_buffer: Dict[Path, StexObject] = dict()
        # THe linked object buffer bufferes all linked objects
        self._linked_object_buffer: Dict[Path, StexObject] = dict()

    def _compile_file_with_respect_to_workspace(self, file: Path) -> Optional[StexObject]:
        ' Compiles or loads the file using external information from the linter\'s workspace member. '
        if self.compiler.recompilation_required(file, self.workspace.get_time_buffer_modified(file)):
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

    def compile_workspace(self) -> Iterable[StexObject]:
        ''' Compiles or loads all files in the workspace and bufferes them in ram.

        This should be called after creating a linter with the @enable_global_validation flag on.
        Doings so will enable the linter to take every single file in the workspace and create better diagnostics.

        Every file present in self.workspace.files will be iterated over.
        '''
        class WorkspaceCompileIter:
            def __init__(self, linter: Linter) -> None:
                self.linter = linter
                self.files = list(self.linter.workspace.files)
                self._len = len(self.linter.workspace.files)

            def __iter__(self) -> Iterator[StexObject]:
                dict_update_buffer: Dict[Path, StexObject] = {}
                with Pool(self.linter.num_jobs) as pool:
                    mapfn = map if self.linter.num_jobs < 1 else pool.imap
                    it = mapfn(self.linter._compile_file_with_respect_to_workspace, self.files)
                    for file, obj in zip(self.files, it):
                        # Need to buffer the dict update because of multiprocessing pickling the whole linter
                        dict_update_buffer[file] = obj
                        yield obj
                self.linter._object_buffer.update(dict_update_buffer)

            def __len__(self) -> int:
                return self._len
        return WorkspaceCompileIter(self)

    def compile_related(self, file: Path, on_progress_fun: Callable[[str, int, int], None] = None) -> Dict[Path, StexObject]:
        ''' Compiles all dependencies of the file, the file itself and updates the buffer.

        Parameters:
            file: The file which will be compiled and from which the related files will be extracted.

        Returns:
            Index of objects with their file path as key.
        '''
        queue = { file }
        visited: Dict[Path, StexObject] = { }
        while queue:
            file = queue.pop()
            if file in visited:
                continue
            if on_progress_fun: on_progress_fun(file, len(visited))
            obj = self._compile_file_with_respect_to_workspace(file)
            visited[file] = obj
            self._object_buffer[file] = obj
            for dep in obj.dependencies:
                if dep.file_hint in visited or dep.file_hint in queue:
                    continue
                queue.add(dep.file_hint)
        return visited

    def lint(self, file: Path, on_progress_fun: Callable[[str, int, bool], None] = None) -> LintingResult:
        ''' Lints the provided @file.

        An optional progress tracking function can be supplied.
        The arguments are current step information (str), number of steps done (int).
        The last argument is a bool flag indicating that the process is done if set to True.

        Parameters:
            file: The file to lint.
            on_progress_fun: Optional progress tracking function which takes step information, steps done
                and a flag indicating that the process is done if True.

        Returns:
            The result of the linting process for the provided @file path.
        '''
        # TODO: Maybe on_progress_fun is overkill here, as its genereally really fast anyway
        if on_progress_fun: on_progress_fun('Preparing', 0, False)
        if file in self._linked_object_buffer and not self._linked_object_buffer[file].check_if_any_related_file_is_newer_than_this_object(self.workspace):
            ln = self._linked_object_buffer[file]
            if on_progress_fun: on_progress_fun('Done', 1, True)
        else:
            objects: Dict[Path, StexObject] = self.compile_related(
                file=file,
                on_progress_fun=lambda *args: on_progress_fun(*args, False) if on_progress_fun else None)
            if on_progress_fun: on_progress_fun('Linking', len(objects), False)
            ln = self.linker.link(file, objects, self.compiler)
            self._linked_object_buffer[file] = ln
            more_objects = self._object_buffer if self.enable_global_validation else {}
            if on_progress_fun: on_progress_fun('Validating', len(objects) + 1, False)
            self.linker.validate_object_references(ln, more_objects=more_objects)
            if on_progress_fun: on_progress_fun('Done', len(objects) + 2, True)
        return LintingResult(ln)

    def definitions(self, file: Path, position: Position) -> List[Location]:
        ' Finds definitions for the symbol under @position in @file. '
        obj: StexObject = self._linked_object_buffer.get(file)
        if not obj:
            return []
        return [definition.location for definition in obj.get_definitions_at(position)]

    def references(self, file: Path, position: Position) -> List[Location]:
        ' Finds references to the symbol under @position in @file. '
        # TODO
        return []
