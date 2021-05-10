import logging
from multiprocessing import Pool
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Iterator, List, Optional, Set

from ..stex.compiler import Compiler, ObjectfileNotFoundError, StexObject
from ..stex.diagnostics import Diagnostic, DiagnosticSeverity
from ..stex.linker import Linker
from ..util.workspace import Workspace
from ..vscode import Location, Position

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

    def format_messages(
            self,
            format_string: str = '{relative_file}:{line}:{column} {severity} - {message} ({code})',
            diagnosticlevel: DiagnosticSeverity = DiagnosticSeverity.Information) -> List[str]:
        """ Formats all errors according to the provided @format_string and @diagnosticlevel.

        Parameters:
            format_string: A str.format format. Available variables are uri, file, filename, relative_file, line, column, code, severity and message.
            diagnosticlevel: The max severity level printet.

        Return:
            List of messages formatted as strings.
        """
        file = self.object.file
        filename = file.name
        uri = file.as_uri()
        messages: List[str] = []
        try:
            relative_file = file.relative_to(Path.cwd())
        except Exception:
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
            messages.append(msg)
        return messages

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
                diagnostics related to references and other things. To prefetch all objects use @Linter.compile_workspace().
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

    def get_files_that_require_recompilation(self) -> Dict[Path, Optional[str]]:
        ' Filters out the files that need recompilation and returns them together with their buffered content. '
        files = dict()
        for file in self.workspace.files:
            if self.compiler.recompilation_required(file, self.workspace.get_time_buffer_modified(file)):
                files[file] = self.workspace.read_buffer(file)
        return files

    def compile_file_with_respect_to_workspace(self, file: Path) -> Optional[StexObject]:
        ' Compiles the file with the buffered content stored in workspace. '
        try:
            return self.compiler.compile(file, content=self.workspace.read_buffer(file))
        except FileNotFoundError:
            log.warning('Failed to compile file "%s": FileNotFound', file)
        return None

    def get_objectfile(self, file: Path) -> Optional[StexObject]:
        """ Retrieves the object of `file`.

        If the file already has been compiled and not changed, a
        buffered StexObject will be returned.

        Returns:
            Optional[StexObject]: Object compiled from `file`. None if `file` does not contain an object.
        """
        try:
            if self.compiler.recompilation_required(file, self.workspace.get_time_buffer_modified(file)):
                return self.compile_file_with_respect_to_workspace(file)
        except Exception:
            log.exception('Failed to compile file %s', file)
        try:
            return self.compiler.load_from_objectfile(file)
        except ObjectfileNotFoundError:
            log.warning('ObjectfileNotFound: "%s"', file)
        return None

    def compile_workspace(self) -> Iterable[Path]:
        ''' Compiles or loads all files in the workspace and bufferes them in ram.

        This should be called after creating a linter with the `enable_global_validation` flag on.
        Doings so will enable the linter to take every single file in the workspace and create better diagnostics.

        Every file present in `self.workspace.files` will be iterated over.

        Returns:
            Iterable[Path]: Iterable that yields the path to the file currently being compiled.
        '''
        class CompilationIterator:
            compiled_object_buffer: Dict[Path, StexObject] = dict()
            files = list(self.workspace.files)
            linter = self

            def __len__(self) -> int:
                return len(self.files)

            def __iter__(self) -> Iterator[Path]:
                compiled_object_buffer: Dict[Path, StexObject] = dict()
                if not self.files:
                    return
                with Pool(self.linter.num_jobs) as pool:
                    it: Iterable[Optional[StexObject]] = pool.imap(
                        self.linter.get_objectfile, self.files)
                    yield self.files[0]
                    for i, obj in enumerate(it, 1):
                        if obj:
                            compiled_object_buffer[obj.file] = obj
                        if i < len(self.files):
                            yield self.files[i]
                self.linter._object_buffer.update(compiled_object_buffer)
        return CompilationIterator()

    def compile_related(self, file: Path) -> Dict[Path, StexObject]:
        ''' Compiles all dependencies of the file, the file itself and updates the buffer.

        Parameters:
            file (Path): The file which will be compiled and from which the related files will be extracted.

        Returns:
            Dict[Path, StexObject]: Index of objects with their file path as key.
        '''
        queue = {file}
        visited: Dict[Path, StexObject] = {}
        while queue:
            file = queue.pop()
            if file in visited:
                continue
            # TODO: Currently forced to reload every file that is used from disk and overwrite the _object_buffer, this should not be necessary
            # TODO: Only overwrite files that actually changed
            # TODO: Only load files that are not already in self._object_buffer
            obj = self.get_objectfile(file)
            if obj is None:
                continue
            visited[file] = obj
            self._object_buffer[file] = obj
            for dep in obj.dependencies:
                if dep.file_hint in visited or dep.file_hint in queue:
                    continue
                queue.add(dep.file_hint)
        return visited

    def lint(self, file: Path) -> LintingResult:
        ''' Lint a file.

        Parameters:
            file (Path): The file to lint.

        Returns:
            LintingResult: The result of the linting process.
        '''
        if (file in self._linked_object_buffer
            and not self._linked_object_buffer[file]
                .check_if_any_related_file_is_newer_than_this_object(self.workspace)):
            ln = self._linked_object_buffer[file]
        else:
            objects: Dict[Path, StexObject] = self.compile_related(file=file)
            ln = self.linker.link(file, objects, self.compiler)
            self._linked_object_buffer[file] = ln
            more_objects = self._object_buffer if self.enable_global_validation else {}
            self.linker.validate_object_references(
                ln, more_objects=more_objects)
        return LintingResult(ln)

    def find_dependent_files_of(self, file: Path, *, _already_added_set: Set[Path] = None) -> Set[Path]:
        """ Find all files that depend on `file`.

        Args:
            file (Path): Path to file.
            _already_added_set (Set[Path], optional): Accumulator for the result. Defaults to None.

        Returns:
            Set[Path]: A set of paths that contain objects that reference `file`.
        """
        dependent_files_set = _already_added_set or set()
        for obj in self._object_buffer.values():
            if file in obj.related_files:
                if file not in dependent_files_set:
                    dependent_files_set.add(obj.file)
                    self.find_dependent_files_of(
                        obj.file, _already_added_set=dependent_files_set)
                else:
                    dependent_files_set.add(obj.file)
        return dependent_files_set

    def definitions(self, file: Path, position: Position) -> List[Location]:
        """ Get list of definition locations for all symbols under the position.

        Args:
            file (Path): File of the position.
            position (Position): Position of the cursor.

        Returns:
            List[Location]: List of locations to where any symbols under the cursor are defined at.
        """
        obj = self._linked_object_buffer.get(file)
        if not obj:
            return []
        return [symbol.location for symbol in obj.get_definitions_at(position)]

    def references(self, file: Path, position: Position) -> List[Location]:
        ' Finds references to the symbol under @position in @file. '
        obj = self._linked_object_buffer.get(file)
        if not obj:
            return []
        definition_locations = set(
            definition.location for definition in obj.get_definitions_at(position))

        references: List[Location] = []
        for obj in self._linked_object_buffer.values():
            for ref in obj.references:
                for refsymb in ref.resolved_symbols:
                    if refsymb.location in definition_locations:
                        references.append(
                            Location(obj.file.as_uri(), ref.range))
                        break

        return references + list(definition_locations)
