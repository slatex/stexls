from pathlib import Path
from typing import List, Optional, Set, Union


class IgnoreFile:
    def __init__(self, ignorefile: Union[str, Path], root: Optional[Union[str, Path]] = None) -> None:
        """ Implements a simple parser for ignore files.

        The ignore file consists of one glob pattern per line.
        Each pattern will be resolved into all possible files it matches
        on initialization or by using `load` to reload the patterns.

        Args:
            ignorefile (str | Path): Path to the file with ignore and include glob patterns.
            root (str | Path, optional): Path to the root the patterns start matching from.
        """
        self.ignorefile = Path(ignorefile).expanduser().resolve().absolute()
        self.root = Path(root).expanduser().resolve().absolute(
        ) if root else self.ignorefile.parent.absolute()
        self.ignore_globs: Set[str] = set()
        self.include_globs: Set[str] = set()
        try:
            self.load()
        except Exception:
            pass

    def load(self):
        """ Parses the ignore file according to the current directory structure of the `root` directory.
        """
        content = self.ignorefile.read_text()
        lines: List[str] = content.split('\n')
        self.include_globs = {
            path.expanduser().resolve().as_posix()
            for line in lines
            if line.strip().startswith('!')
            if line.strip()[1:].strip()
            for path in self.root.rglob(line.strip()[1:].strip())
        }
        self.ignore_globs = {
            path.expanduser().resolve().as_posix()
            for line in lines
            if not line.strip().startswith('!')
            if line.strip()
            for path in self.root.rglob(line.strip())
            if not any(map(lambda ancestor: ancestor.as_posix() in self.include_globs, path.parents))
        }

    def match(self, path: Path) -> bool:
        """ Matches a path with the ignore patterns and returns wether the path is ignored or not.

        Args:
            path (Path): Path to test.

        Returns:
            bool: True if the `path` is ignored, False otherwise.
        """
        try:
            path = (self.root/path).expanduser().resolve(
            ).absolute().relative_to(self.root)
        except ValueError:
            return False

        for ancestor in (path, *path.parents):
            if (self.root/ancestor).as_posix() in self.ignore_globs:
                for ancestor in (path, *path.parents):
                    if (self.root/ancestor).as_posix() in self.include_globs:
                        return False
                return True
        return False
