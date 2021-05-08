import glob
import itertools
import logging
import re
import time
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Pattern, Set, Union

from .. import vscode

log = logging.getLogger(__name__)

__all__ = ['Workspace']


class TextDocument:
    def __init__(self, path: Path, version: int, text: str) -> None:
        """ Versioned text document being tracked because it's in the workspace.

        Args:
            path (Path): Path to the text document.
            version (int): Version number.
            text (str): Buffered contents of the file.
        """
        self.path: Path = path
        self.version: int = version
        self.text: str = text
        self.time_modified: float = time.time()

    def update(self, version: int, text: str):
        ' Updates the version, text and time modified timestamp of this text document. '
        self.version = version
        self.text = text
        self.time_modified = time.time()


class Workspace:
    def __init__(self, root: Path):
        """ Opens a workspace folder `root`.

        The workspace allows to query and filter the files in the workspace
        and additionally can keep track of the state of modified files.

        Args:
            root (Path): Path to workspace folder.
        """
        self.root = Path(root).expanduser().resolve().absolute()
        # Map of files to a tuple of file time modified and content
        self._open_files: Dict[Path, TextDocument] = {}
        self._ignore: Optional[List[Pattern]] = None
        self._include: Optional[List[Pattern]] = None

    def is_open(self, file: Path) -> bool:
        ' Returns true if a modified version of this file that can be queried with read_file() is in memory. '
        return file in self._open_files

    def get_version(self, file: Path) -> Optional[int]:
        ' Returns the version of the file if it is added. '
        if self.is_open(file):
            return self._open_files[file].version
        return None

    def get_time_buffer_modified(self, file: Path) -> float:
        ' Retrieves the timestamp since the last edit to the buffered file. Returns 0 if the file is not open. '
        if self.is_open(file):
            return self._open_files[file].time_modified
        return 0

    def get_time_modified(self, file: Path) -> float:
        ' Get the time the file was last modified either in buffer or on disk. 0 if the file is not open. '
        if self.is_open(file):
            return self.get_time_buffer_modified(file)
        if file.is_file():
            return file.lstat().st_mtime
        return 0

    def open_file(self, path: Path, version: int, text: str) -> bool:
        """ Opens a file in the current workspace.

            This is needed to be able to handle files which are not saved to disk.
            The client can open a file and allow the the server to read the file
            while the user is modifying it.

        Parameters:
            path: Path of the opened file.
            version: Text document version identifier provided by the language client.
            text: Content of the file when opening it.

        Returns:
            True if the file was successfully opened.
        """
        if path in self._open_files:
            log.warning('File already open: "%s"', path)
            return False
        else:
            log.debug('Opening file: "%s"', path)
        if path not in self.files:
            log.warning(
                'Ignoring open file attempt of "%s" because it is not part of this workspace.', path)
            return False
        self._open_files[path] = TextDocument(path, version, text)
        return True

    def update_file(self, path: Path, version: int, text: str) -> bool:
        ' Updates the time_modified, text and version of an already added file. Returns True on success. '
        if not self.is_open(path):
            log.warning(
                'Unable to update file that has not been opened: "%s"', path)
            return False
        document = self._open_files[path]
        if version < document.version:
            log.warning(
                'Ignoring file update with lower version number: %i < %i', version, document.version)
            return False
        log.debug('Updating version of "%s": from %i to %i',
                  path, document.version, version)
        document.update(version, text)
        return True

    def close_file(self, path: Path) -> bool:
        """ Removes an opened file from ram.

            After a file is closed we don't need to store it's state anymore
            as it will be reported again when it is opened. If another file
            accesses this file, it can just read it from disk.

        Parameters:
            path: The closed file.

        Returns:
            True if the file was closed because it was open.
        """
        if path in self._open_files:
            log.debug('Closing file: "%s"', path)
            del self._open_files[path]
            return True
        else:
            log.warning('Closing not open file: "%s"', path)
        return False

    def read_buffer(self, path: Path) -> Optional[str]:
        """ Reads the file's buffered content. """
        document = self._open_files.get(path)
        if document:
            log.debug('Reading buffered file version %s: "%s"',
                      document.version, path)
            return document.text
        return None

    def read_file(self, path: Path) -> Optional[str]:
        """ Gets the most up to date content of the file @path.

        Returns:
            Reads content from buffer if it exists, else reads the content from disk.
            None is returned if the file is not buffered and the file can't be read from disk.
        """
        if self.is_open(path):
            document = self._open_files[path]
            log.debug('Reading file (version %s) from buffer: "%s"',
                      document.version, path)
            return document.text
        try:
            with open(path) as fd:
                log.debug('Reading local file: "%s"', path)
                return fd.read()
        except Exception:
            log.exception('Failed to read local file from disk: "%s"', path)
        return None

    def read_location(self, location: vscode.Location) -> Optional[str]:
        """ Reads the content of a location.

            This method is already provided by Location.read()
            but because a file may be modified and not stored on disk,
            it may return wrong contents. This allows this method to return
            correct contents for file's of which the content is recorded
            with open_file and update_file_incremental.

        Parameters:
            location: Location to read.

        Returns:
            Content of the location from ram if opened, from disk if not.
            None if any kind of error occurs.
        """
        content = self.read_file(location.path)
        if content is None:
            return None
        return location.read(content.split('\n'))

    @property
    def include(self) -> Union[Pattern, List[Pattern], None]:
        ' Optional include pattern or list of include patterns used to filter the output of Workspace.files. '
        return self._include

    @include.setter
    def include(self, value: Union[Pattern, str, Iterable[Union[Pattern, str]], None]):
        if value is None:
            self._include = None
            return
        if isinstance(value, str) or not isinstance(value, Iterable):
            value = [value]
        self._include = [
            pattern if isinstance(pattern, Pattern) else re.compile(pattern)
            for pattern in value
            if pattern
        ]

    @property
    def ignore(self) -> Union[Pattern, List[Pattern], None]:
        ' Optional ignore pattern or list of include patterns used to filter the output of Workspace.files. '
        return self._ignore

    @ignore.setter
    def ignore(self, value: Union[Pattern, str, Iterable[Union[Pattern, str]], None]):
        if value is None:
            self._ignore = None
            return
        if isinstance(value, str) or not isinstance(value, Iterable):
            value = [value]
        self._ignore = [
            pattern if isinstance(pattern, Pattern) else re.compile(pattern)
            for pattern in value
            if pattern
        ]

    @property
    def files(self) -> Set[Path]:
        ' Returns the set of .tex files in this workspace after they are filtered using ignore and include patterns. '
        # get all files from the workspace root
        glob_pattern = self.root / '**' / 'source' / '**' / '*.tex'
        tex_file_paths = list(
            glob.glob(glob_pattern.as_posix(), recursive=True))
        # filter out non-included files
        if isinstance(self._include, Iterable):
            # list of includes is ORed together
            tex_file_paths = list(
                file
                for pattern in self._include
                for file in filter(pattern.match, tex_file_paths)
            )
        # filter out ignored files
        if isinstance(self._ignore, Iterable):
            # list of ignores is ANDed together
            for pattern in self._ignore:
                tex_file_paths = list(itertools.filterfalse(
                    pattern.match, tex_file_paths))
        # map to paths
        paths = map(Path, tex_file_paths)
        # filter out non-files
        files = filter(lambda p: p.is_file(), paths)
        # remove duplicates
        return set(files)
