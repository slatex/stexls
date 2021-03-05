import collections
import itertools
import os
import re
from glob import glob
from pathlib import Path
from typing import Dict, Optional, Pattern, Union

__all__ = ['WorkspaceWatcher', 'Changes']

Changes = collections.namedtuple('Changes', ['created', 'modified', 'deleted'])


class WorkspaceWatcher:
    """ Watches all files located inside a root workspace folder.

    The watching process is not done asynchronously and not on a file basis.
    Instead, everytime the index is updated, all files inside a folder will be
    checked at once.
    """

    def __init__(self, pattern, include: Union[Pattern, str] = None, ignore: Union[Pattern, str] = None):
        """Initializes the watcher with a pattern of files to watch.

        Args:
            pattern: GLOB pattern of which files to add.
            include: Whitelist REGEX pattern. Used to filter out WANTED files. None to skip include step.
            ignore: Blacklist REGEX pattern. Used to filter out UNWANTED files. None to skip ignore step.
        """
        self.pattern = pattern
        self.include: Optional[Pattern] = (
            re.compile(include)
            if isinstance(include, str)
            else include)
        self.ignore: Optional[Pattern] = (
            re.compile(ignore)
            if isinstance(ignore, str)
            else ignore)
        self.files: Dict[Path, float] = {}

    def update(self) -> Changes:
        """Updates the internal file index.

        Indexes all files inside the workspace directory.
        Returns newly created, deleted files, as well as
        files where the modified time changed from last update() call.

        Returns:
            Changes: Tuple of created, modified and deleted files.
        """
        # split file index into delete and still existing files
        old_files = set(filter(lambda x: os.path.isfile(x), self.files.keys()))
        deleted = set(
            filter(lambda x: not os.path.isfile(x), self.files.keys()))
        # get list of files & folders in the workspace
        files = set(filter(os.path.isfile, glob(self.pattern, recursive=True)))
        # apply whitelist
        if self.include:
            files = set(filter(self.include.match, files))
        # apply blacklist
        if self.ignore:
            files = set(itertools.filterfalse(self.ignore.match, files))
        # create new index of files and modified times
        file_index = dict(
            map(lambda x: (Path(x).absolute(), os.path.getmtime(x)), files))
        # newly created files are the difference of files before and after update
        new_files = set(file_index)
        created = new_files.difference(old_files)
        # modified files are files which exist in before and after update index, with a new timestamp
        modified = set(f for f in old_files.intersection(
            new_files) if self.files[f] != file_index[f])
        # update the file index
        self.files = file_index
        # return changes
        return Changes(created=created, modified=modified, deleted=deleted)
