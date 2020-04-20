import re
import glob
import itertools
import logging
import multiprocessing
import functools
from hashlib import sha1
from pathlib import Path
from typing import List, Iterator, Pattern, Callable, Iterable, Set, Dict

from stexls.util.vscode import *

log = logging.getLogger(__name__)

class Workspace:
    def __init__(self, root: Path):
        """ Opens a workspace with the specified root as root.

        The workspace allows to query and filter the files in the workspace
        and additionally can keep track of the state of modified files.
        """
        self.root = Path(root).expanduser().resolve().absolute()
        self._open_files: Dict[Path, str] = {}
        self._ignore: Optional[List[Pattern]] = None
        self._include: Optional[List[Pattern]] = None

    def is_open(self, file: Path) -> bool:
        ' Returns true if a modified version of this file that can be queried with read_file() is in memory. '
        return file in self._open_files

    def open_file(self, path: Path, content: str):
        """ Opens a file in the current workspace.

            This is needed to be able to handle files which are not saved to disk.
            The client can open a file and allow the the server to read the file
            while the user is modifying it.

        Parameters:
            path: Path of the opened file.
            content: Content of the file when opening it.
        """
        if path in self._open_files:
            log.warning('Opened already open file: "%s"', path)
        else:
            log.debug('Opening file: "%s"', path)
        self._open_files[path] = content

    def update_file_incremental(self, path: Path, content: str):
        """ Incremental update of an opened file.

            This is an optimization provided by the language server protocol
            The client can decide to only report changes to the file and
            the workspace constructs the modified file's state.
            This allows the server to work with files not stored to disk.
        
        Parameters:
            path: The path of the file.
        """
        if path in self._open_files:
            log.debug('Updating file: "%s"', path)
        else:
            log.warning('Updating not open file: "%s"', path)
        self._open_files[path] = content

    def close_file(self, path: Path):
        """ Removes an opened file from ram.

            After a file is closed we don't need to store it's state anymore
            as it will be reported again when it is opened. If another file
            accesses this file, it can just read it from disk.

        Parameters:
            path: The closed file.
        """
        if path in self._open_files:
            log.debug('Closing file: "%s"', path)
            del self._open_files[path]
        else:
            log.warning('Closing not open file: "%s"', path)

    def read_file(self, path: Path) -> Optional[str]:
        """ Reads a file modified in this workspace. If the accessed file is not modified
            it is read from disk instead.
        
        Returns:
            Content of the file. Read from disk if not opened and read from ram if opened.
            If any kind of exception occurs None is returned.
        """
        if path in self._open_files:
            log.debug('Reading open file: "%s"', path)
            return self._open_files[path]
        try:
            with open(path) as fd:
                log.debug('Reading local file: "%s"', path)
                return fd.read()
        except:
            log.exception('Failed to read local file from disk: "%s"', path)
        return None

    def read_location(self, location: Location) -> Optional[str]:
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
        files = list(glob.glob((self.root / '**' / '*.tex').as_posix(), recursive=True))
        # filter out non-included files
        if isinstance(self._include, Iterable):
            # list of includes is ORed together
            files = list(
                file
                for pattern in self._include
                for file in filter(pattern.match, files)
            )
        # filter out ignored files
        if isinstance(self._ignore, Iterable):
            # list of ignores is ANDed together
            for pattern in self._ignore:
                files = list(itertools.filterfalse(pattern.match, files))
        # map to paths
        files = map(Path, files)
        # filter out non-files
        files = filter(lambda p: p.is_file(), files)
        return set(files)
