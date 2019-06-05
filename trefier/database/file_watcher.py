import os.path as path
from glob import glob
from collections import defaultdict

__all__ = ['FileWatcher']

class FileWatcher:
    """ Implements a simple file watcher, that keeps track of deleted and modified status of added files """
    def __init__(self, extensions=['.tex']):
        self._files = defaultdict(list)
        self._extensions = extensions
    
    def update(self):
        """ Removes deleted files from index then returns two lists for deleted and modified files """
        deleted = set(filter(lambda x: not path.isfile(x), self._files))
        modified = set(f for f, time in self._files.items() if path.isfile(f) and time < path.getmtime(f))

        for file in deleted:
            del self._files[file]
        
        for file in modified:
            self._files[file] = path.getmtime(file)

        return deleted, modified

    def add(self, file, pattern=True, add_only=True, mark_modified=True):
        """ Adds all files grabbed by the pattern to the index and if mark_modified is True, returns them on the next update() call
        Returns set of added files
        """
        changed = set()
        for file in glob(file, recursive=True) if pattern else [file]:
            file = path.abspath(file)
            if self._extensions and not any(file.endswith(ext) for ext in self._extensions):
                # skip files that don't match any extensions
                continue
            if add_only and file in self._files:
                # skip already watched file 
                continue
            if path.isfile(file):
                # only add if file is actually a file
                changed.add(file)
                self._files[file] = 0 if mark_modified else path.getmtime(file)
        return changed
    
    def remove(self, file_or_pattern):
        """ Removes all files by glob pattern and returns the list of removed files """
        removed = set(filter(lambda x: x in self._files, map(path.abspath, glob(file_or_pattern, recursive=True))))
        for file in removed:
            del self._files[file]
        return removed
    
    def __iter__(self):
        """ Iterator for watched files """
        return iter(self._files)
