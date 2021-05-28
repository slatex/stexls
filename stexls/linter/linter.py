import logging
import re
from multiprocessing import Pool
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set

from ..stex.compiler import Compiler, StexObject
from ..stex.diagnostics import Diagnostic, DiagnosticSeverity
from ..stex.linker import Linker
from ..trefier.models.seq2seq import Seq2SeqModel
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
                 max_trefier_file_size_kb: int = 50,
                 max_lint_file_size_kb: int = 100):
        """ Initializes a linter object.

        Parameters:
            workspace: Workspace this linter works on.
            outdir: Output directory to where the compiler will store it's output at.
            max_trefier_file_size_kb: The maximum file size (Kilo Byte) the trefier will accept as input.
                If the file is larger, then no tags will be made.
            max_lint_file_size_kb: The maximum file size (Kilo Byte) the linter will accept as input.
                If the file is larger, then only the diagnostics that can be made using
                only that file alone are published.
        """
        self.workspace = workspace
        self.outdir = outdir or (Path.cwd() / 'objects')
        self.compiler = Compiler(self.workspace.root, self.outdir)
        self.linker = Linker(self.outdir)
        # The objectbuffer stores all compiled objects
        self.unlinked_object_buffer: Dict[Path, StexObject] = dict()
        # The linked object buffer bufferes all linked objects
        self.linked_object_buffer: Dict[Path, StexObject] = dict()
        # Maximum file size that the trefier is applied to
        self.max_trefier_file_size_kb = max_trefier_file_size_kb
        # Maximum file size the linter is allowed to lint
        self.max_lint_file_size_kb = max_lint_file_size_kb

    def get_files_that_require_recompilation(self) -> Dict[Path, Optional[str]]:
        ' Filters out the files that need recompilation and returns them together with their buffered content. '
        files = dict()
        for file in self.workspace.files:
            if self.compiler.recompilation_required(file, self.workspace.get_time_buffer_modified(file)):
                files[file] = self.workspace.read_buffer(file)
        return files

    def get_objectfile(self, file: Path) -> Optional[StexObject]:
        """ Retrieves the object of `file`.

        If the file already has been compiled and not changed, a
        buffered StexObject will be returned.

        This is a shortcut for `Compiler.compile_or_load_file`
        that automatically reads buffered content and time buffer
        time modified.

        Returns:
            Optional[StexObject]: The objectfile for `file`. None if an error occured.
        """
        return self.compiler.compile_or_load_from_file(
            file,
            content=self.workspace.read_buffer(file),
            time_modified=self.workspace.get_time_buffer_modified(file)
        )

    def compile_workspace(self, limit: int = 10000, num_jobs: int = 1) -> List[Path]:
        ''' Compiles or loads all files in the workspace.

        The objects will be buffered and will be later used to
        create diagnostics that otherwise can not be created
        because some files have not been compield and buffered yet.

        Args:
            limit (int, optional): Maximum number of files that are compiled.
                If set to 0, then no files are compiled, while -1 removes the limit.
                Defaults to 10000.
            num_jobs (int, optional): Number of processes to use for multiprocessing. Defaults to 1.

        Returns:
            List[Path]: Paths to files with objects in the workspace.
        '''
        files = list(self.workspace.files)
        if limit >= 0:
            files = files[:limit]
        content = list(map(self.workspace.read_buffer, files))
        time_modified = list(
            map(self.workspace.get_time_buffer_modified, files))
        args = zip(files, content, time_modified)
        with Pool(num_jobs) as pool:
            it: Iterable[Optional[StexObject]] = pool.starmap(
                self.compiler.compile_or_load_from_file, args)
        paths = []
        for obj in filter(None, it):
            paths.append(obj.file)
            self.unlinked_object_buffer[obj.file] = obj
        return paths

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
            self.unlinked_object_buffer[file] = obj
            for dep in obj.dependencies:
                if dep.file_hint in visited or dep.file_hint in queue:
                    continue
                queue.add(dep.file_hint)
        return visited

    def lint(self, file: Path, model: Optional[Seq2SeqModel] = None) -> LintingResult:
        ''' Lint a file.

        Parameters:
            file (Path): The file to lint.

        Returns:
            LintingResult: The result of the linting process.
        '''
        if file.is_file():
            size = file.stat().st_size // 1024
            if self.max_lint_file_size_kb > 0 and self.max_lint_file_size_kb < size:
                # Guard linting too large files
                log.warning(
                    'Skipping linting of large file of size %iKB: %s', size, str(file))
                return LintingResult(self.unlinked_object_buffer.get(file, StexObject(file)))
            objects: Dict[Path, StexObject] = self.compile_related(file=file)
            ln = self.linker.link(file, objects, self.compiler)
            if model is None:
                pass
            elif self.max_trefier_file_size_kb > 0 and self.max_trefier_file_size_kb < size:
                # Guard trefying too large files
                log.warning(
                    'Rejecting to use trefier on large file of size %iKB: "%s"', size, str(file))
            else:
                log.debug('Adding trefier tags for file: %s', file)
                tags, = model.predict(file)
                env_pattern = re.compile(
                    r'[ma]*(Tr|tr|D|d|Dr|dr)ef[ivx]+s?\*?|gimport\*?|(import|use)(mh)?module\*?|(sym|var)def\*?|sym[ivx]+\*?|[tv]assign|libinput|\$')
                for tag in tags:
                    if not isinstance(tag.label, float) or not 0 <= tag.label <= 1:
                        loc = Location(file.as_uri(), tag.token.range)
                        log.warning('Encountered invalid tag value "%s" at %s:%s',
                                    tag.label, file.as_uri(), tag.token.range)
                        continue
                    if round(tag.label) and not any(map(env_pattern.fullmatch, tag.token.envs)):
                        loc = Location(file.as_uri(), tag.token.range)
                        log.debug('Tagging %s with %s',
                                  loc.format_link(), tag.label)
                        ln.diagnostics.trefier_tag(
                            tag.token.range, tag.token.lexeme, tag.label)
            self.linked_object_buffer[file] = ln
            self.linker.validate_object_references(ln)
        return LintingResult(ln)

    def find_users_of_file(self, file: Path) -> Set[Path]:
        """ Find all files that use symbols in from `file`.

        Args:
            file (Path): Path to file.

        Returns:
            Set[Path]: A set of paths that contain objects that reference `file`.
        """
        dependent_files_set = set()
        for obj in self.unlinked_object_buffer.values():
            if file in obj.related_files:
                dependent_files_set.add(obj.file)
            elif obj.file in self.linked_object_buffer:
                obj = self.linked_object_buffer[obj.file]
                for ref in obj.references:
                    if any(resolved.location.path == file for resolved in ref.resolved_symbols):
                        dependent_files_set.add(obj.file)
                        break
        if file in dependent_files_set:
            dependent_files_set.remove(file)
        return dependent_files_set

    def definitions(self, file: Path, position: Position) -> List[Location]:
        """ Get list of definition locations for all symbols under the position.

        Args:
            file (Path): File of the position.
            position (Position): Position of the cursor.

        Returns:
            List[Location]: List of locations to where any symbols under the cursor are defined at.
        """
        obj = self.linked_object_buffer.get(file)
        if not obj:
            return []
        return [symbol.location for symbol in obj.get_definitions_at(position)]

    def references(self, file: Path, position: Position) -> List[Location]:
        """ Finds references to the symbol under `position` in `file`.

        Args:
            file (Path): File.
            position (Position): Position of the cursor.

        Returns:
            List[Location]: List of locations where references to the
                symbol under the cursor are located.
        """
        obj = self.linked_object_buffer.get(file)
        if not obj:
            return []
        definition_locations = set(
            definition.location for definition in obj.get_definitions_at(position))

        references: List[Location] = []
        for obj in self.linked_object_buffer.values():
            for ref in obj.references:
                for refsymb in ref.resolved_symbols:
                    if refsymb.location in definition_locations:
                        references.append(
                            Location(obj.file.as_uri(), ref.range))
                        break

        return references + list(definition_locations)
