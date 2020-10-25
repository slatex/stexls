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

    def format_messages(self, format_string: str = '{relative_file}:{line}:{column} {severity} - {message} ({code})', diagnosticlevel: DiagnosticSeverity = DiagnosticSeverity.Information) -> List[str]:
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
        ' Gets the objectfile by compiling it or loading it from disk if already compiled and no recompilation is required. '
        try:
            if self.compiler.recompilation_required(file, self.workspace.get_time_buffer_modified(file)):
                return self.compile_file_with_respect_to_workspace(file)
        except:
            log.exception('Failed to compile file %s', file)
        try:
            return self.compiler.load_from_objectfile(file)
        except ObjectfileNotFoundError:
            log.warning('ObjectfileNotFound: "%s"', file)
        return None

    def compile_workspace(self) -> Iterable[Optional[Path]]:
        ''' Compiles or loads all files in the workspace and bufferes them in ram.

        This should be called after creating a linter with the @enable_global_validation flag on.
        Doings so will enable the linter to take every single file in the workspace and create better diagnostics.

        Every file present in self.workspace.files will be iterated over.

        Returns:
            Iterable that yields the path to the file currently being compiled.
        '''
        class WorkspaceCompileIter:
            def __init__(self, linter: Linter) -> None:
                self.linter = linter
                self._files = list(self.linter.workspace.files)
                # Length is -1 because the last file has no "next"
                self._len = max(0, len(self._files) - 1)
                self.compiled_object_buffer: Dict[Path, StexObject] = dict()

            def __iter__(self) -> Iterator[Optional[Path]]:
                with Pool(self.linter.num_jobs) as pool:
                    mapfn = map if self.linter.num_jobs <= 1 else pool.imap
                    it = mapfn(self.linter.get_objectfile, self._files)
                    # Rotate the file list by one in order be able to view the file being compiled after the current obj
                    next_files = [*self._files[1:], None]
                    # Iterate through the list next files paired with the object of the currently compiled file
                    for next_file, obj in zip(next_files, it):
                        if obj:
                            # Need to buffer the dict update because of multiprocessing pickling the whole linter
                            self.compiled_object_buffer[obj.file] = obj
                        if next_file:
                            # The last element has no next, don't yield anything
                            yield next_file
                self.linter._object_buffer.update(self.compiled_object_buffer)

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
            # TODO: Currently forced to reload every file that is used from disk and overwrite the _object_buffer, this should not be necessary
            # TODO: Only overwrite files that actually changed
            # TODO: Only load files that are not already in self._object_buffer
            obj = self.get_objectfile(file)
            if not obj:
                continue
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

    def find_dependent_files_of(self, file: Path, *, _already_added_set: Set[Path] = None) -> Set[Path]:
        """ Finds all files that somehow depend on or reference the argument @file, given that their object is buffered. """
        dependent_files_set = _already_added_set or set()
        for obj in self._object_buffer.values():
            if file in obj.related_files:
                if file not in dependent_files_set:
                    dependent_files_set.add(obj.file)
                    self.find_dependent_files_of(obj.file, _already_added_set=dependent_files_set)
                else:
                    dependent_files_set.add(obj.file)
        return dependent_files_set

    def definitions(self, file: Path, position: Position) -> List[Location]:
        ' Finds definitions for the symbol under @position in @file. '
        obj: StexObject = self._linked_object_buffer.get(file)
        if not obj:
            return []
        return [symbol.location for symbol in obj.get_definitions_at(position)]

    def references(self, file: Path, position: Position) -> List[Location]:
        ' Finds references to the symbol under @position in @file. '
        obj: StexObject = self._linked_object_buffer.get(file)
        if not obj:
            return []
        definition_locations = set(definition.location for definition in obj.get_definitions_at(position))

        references : List[Location] = []
        for obj in self._linked_object_buffer.values():
            for ref in obj.references:
                for refsymb in ref.resolved_symbols:
                    if refsymb.location in definition_locations:
                        references.append(Location(obj.file.as_uri(), ref.range))
                        break

        return references + list(definition_locations)
