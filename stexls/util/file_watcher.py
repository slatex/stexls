from typing import Dict, List, Awaitable, Union
from glob import glob
import os
import itertools
import collections
import asyncio
from pathlib import Path

__all__ = ['WorkspaceWatcher', 'AsyncFileWatcher']

class WorkspaceWatcher:
    """ Watches all files located inside a root workspace folder.

    The watching process is not done asynchronously and not on a file basis.
    Instead, everytime the index is updated, all files inside a folder will be
    checked at once.
    """
    Changes = collections.namedtuple('Changes', ['created', 'modified', 'deleted'])
    def __init__(self, pattern: 'glob'):
        """Initializes the watcher with a pattern of files to watch.

        Args:
            pattern (glob): Pattern of files to add.
        """
        self.pattern = pattern
        self.files: Dict[Path, float] = {}

    def __getstate__(self):
        return (self.folder, self.filter, self.files)

    def __setstate__(self, state):
        self.folder, self.filter, self.files = state

    def update(self) -> 'WorkspaceWatcher.Changes':
        """Updates the internal file index.

        Indexes all files inside the workspace directory.
        Returns newly created, deleted files, as well as
        files where the modified time changed from last update() call.

        Returns:
            WorkspaceWatcher.Changes: Tuple of created, modified and deleted files.
        """
        # split file index into delete and still existing files
        old_files = set(filter(lambda x: os.path.isfile(x), self.files.keys()))
        deleted = set(filter(lambda x: not os.path.isfile(x), self.files.keys()))
        # get list of files & folders in the workspace
        files = glob(self.pattern, recursive=True)
        # filter out files
        files = filter(os.path.isfile, files)
        # create new index of files and modified times
        files = dict(map(lambda x: (Path(x), os.path.getmtime(x)), files))
        # newly created files are the difference of files before and after update
        new_files = set(files)
        created = new_files.difference(old_files)
        # modified files are files which exist in before and after update index, with a new timestamp
        modified = set(f for f in old_files.intersection(new_files) if self.files[f] != files[f])
        # update the file index
        self.files = files
        # return changes
        return WorkspaceWatcher.Changes(created=created, modified=modified, deleted=deleted)


class AsyncFileWatcher:
    ''' Asynchronous file watcher which is able to emit
    created, deleted and modified events for a single file.
    '''
    def __init__(self, path: str, binary: bool = False):
        """Initializes the watcher.

        The file watcher is able to watch files which do not exist yet
        and will emit created events, when it is created.

        The respective events will be stored in the events_on_* members.

        Args:
            path (str): Path to the watched file.
            binary (bool): Whether or not the file should be read in binary or not. Defaults to False.
        """
        self.path = path
        self.binary = binary
        self.events_on_created: List[asyncio.Future] = []
        self.events_on_deleted: List[asyncio.Future] = []
        self.events_on_modified: List[asyncio.Future] = []
        self._watching = False

    def __getstate__(self):
        return (self.path, self.binary)

    def __setstate__(self, state):
        self.path, self.binary = state
        self.events_on_created = []
        self.events_on_deleted = []
        self.events_on_modified = []
        self._watching = False

    async def watch(self, delay: float = 2.0):
        """Starts an infinite loop watching for file changes.

        The watching process can be safely stopped by cancelling
        the watch() coroutine. If cancelled, all waiting events
        will also be cancelled or resolved with False.

        Args:
            delay (float, optional): Poll frequency in seconds. Defaults to 2.0.

        Raises:
            ValueError: Raised if watcher is already running.
        """
        if self._watching:
            raise ValueError('Watcher already active.')
        self._watching = True
        try:
            while True:
                if os.path.isfile(self.path):
                    try:
                        await self._watch_modified(delay)
                    except FileNotFoundError:
                        self._resolve(self.events_on_deleted, True)
                else:
                    await self._watch_created(delay)
        finally:
            self._watching = False
            self._cleanup()

    def _cleanup(self):
        ' Cancels all waiting events and clears event lists. '
        for evt in itertools.chain(
            self.events_on_created,
            self.events_on_modified):
            if not evt.cancelled():
                evt.cancel()
        for evt in self.events_on_deleted:
            if not evt.cancelled():
                evt.set_result(False)
        self.events_on_modified.clear()
        self.events_on_deleted.clear()
        self.events_on_created.clear()

    def on_modified(self) -> Awaitable[Union[bytes, str]]:
        """Creates an event which is triggered if the file changes.

        Creation of a file is not a change and will not trigger this event.
        Use on_created() instead.

        Raises:
            ValueError: Raised if the file watcher is not running.

        Returns:
            Awaitable[Union[bytes, str]]: Awaitable future which resolves to the new content of the file.
                Cancelled when the watcher is cancelled.
        """
        if not self._watching:
            raise ValueError('File watcher not running.')
        evt = asyncio.Future()
        self.events_on_modified.append(evt)
        return evt

    def on_created(self) -> Awaitable[str]:
        """Creates an event which is triggered when the file is created.

        Raises:
            ValueError: Raised if the file watcher is not running.

        Returns:
            Awaitable[str]: Resolves to the content of the file when it is created.
                Cancelled if the watcher is cancelled.
        """
        if not self._watching:
            raise ValueError('File watcher not running.')
        evt = asyncio.Future()
        self.events_on_created.append(evt)
        return evt

    async def on_created_or_modified(self) -> Awaitable[str]:
        done, pending = await asyncio.wait((
            self.on_created(),
            self.on_modified()
        ), return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        for task in done:
            return task.result()

    def on_deleted(self) -> Awaitable[bool]:
        """Creates an event which is triggered when the file is deleted.

        Raises:
            ValueError: Raised if the file watcher is not running.

        Returns:
            Awaitable[bool]: Resolves to True when the file is deleted,
                Resolves to False if the watcher is stopped.
        """
        if not self._watching:
            raise ValueError('File watcher not running.')
        evt = asyncio.Future()
        self.events_on_deleted.append(evt)
        return evt

    def _read(self) -> Union[str, bytes]:
        """Reads the file's content.

        Returns:
            Union[str, bytes]: Content is bytes if self.binary is set, else string.
        """
        with open(self.path, 'rb' if self.binary else 'r') as fd:
            return fd.read()

    def _timestamp(self):
        ' Returns the modified timestamp of the file. '
        return os.stat(self.path).st_mtime

    async def _watch_modified(self, delay: float):
        """Watches an existing file for changes.

        Loop is infinite and can only be stopped by deleting the watched file.
        The loop polls the file's status every delay seconds and triggers
        on_modified events if the modified time has changed.

        Args:
            delay (float): Poll delay.
        """
        timestamp = self._timestamp()
        while True:
            new_timestamp = self._timestamp()
            if timestamp != new_timestamp:
                content = self._read()
                self._resolve(self.events_on_modified, content)
                timestamp = new_timestamp
            await asyncio.sleep(delay)

    async def _watch_created(self, delay: float):
        """Waits until the watched file is created.

        Checks the file path every delay seconds.
        Triggers on_created events if the file exists,
        then returns.

        Args:
            delay (float): Poll delay in seconds.
        """
        while not os.path.isfile(self.path):
            await asyncio.sleep(delay)
        self._resolve(self.events_on_created, self._read())

    def _resolve(self, events: List[asyncio.Future], value):
        ' Resolves a list of events with a given value. '
        for evt in events:
            if not evt.cancelled():
                evt.set_result(value)
        events.clear()
