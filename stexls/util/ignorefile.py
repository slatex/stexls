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
        self.ignorefile = Path(ignorefile)
        self.root = Path(root) if root else self.ignorefile.parent
        self.ignored_paths: Set[Path] = set()
        self.load()

    def load(self):
        try:
            content = self.ignorefile.read_text()
        except Exception:
            return
        lines: List[str] = content.split('\n')
        include_globs = {
            line.strip()[1:].strip()
            for line in lines
            if line.strip().startswith('!')
        }
        ignore_globs = {
            line.strip()
            for line in lines
            if not line.strip().startswith('!')
        }
        include_files = {
            path
            for glob in include_globs
            if glob
            for path in self.root.rglob(glob)
        }
        self.ignored_paths: Set[str] = {
            str(path)
            for glob in ignore_globs
            if glob
            for path in self.root.rglob(glob)
            if not any(str(path).startswith(str(included)) for included in include_files)
        }

    def match(self, path: Path) -> bool:
        try:
            path = Path(path).absolute().relative_to(self.root)
        except ValueError:
            return False
        cond = Path('.')
        while path != cond:
            if str(self.root / path) in self.ignored_paths:
                return True
            path = path.parent
        return False
