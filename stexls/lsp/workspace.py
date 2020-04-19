import re
import glob
import itertools
import logging
import multiprocessing
import functools
from hashlib import sha1
from pathlib import Path
from typing import List, Iterator, Pattern, Callable, Iterable, Set, Dict

from stexls.stex import parser, linker
from stexls.stex.compiler import StexObject
from stexls.util.vscode import *

log = logging.getLogger(__name__)

class Workspace:
    def __init__(self, root: Path):
        self.root = Path(root).expanduser().resolve().absolute()
        self._ignore: Pattern = None
        self._include: Pattern = None

    @property
    def include(self) -> Pattern:
        return self._include

    @include.setter
    def include(self, value: Optional[Pattern]):
        self._include = value if not value or isinstance(value, Pattern) else re.compile(value)

    @property
    def ignore(self) -> Pattern:
        return self._ignore

    @ignore.setter
    def ignore(self, value: Optional[Pattern]):
        self._ignore = value if not value or isinstance(value, Pattern) else re.compile(value)

    @property
    def files(self) -> Set[Path]:
        # get all files from the workspace root
        files = glob.glob((self.root / '**' / '*.tex').as_posix(), recursive=True)
        # filter out non-included files
        if self._include:
            files = filter(self._include.match, files)
        # filter out ignored files
        if self._ignore:
            files = itertools.filterfalse(self._ignore.match, files)
        # map to paths
        files = map(Path, files)
        # filter out non-files
        files = filter(lambda p: p.is_file(), files)
        return set(files)
