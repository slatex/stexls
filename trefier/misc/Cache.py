from __future__ import annotations
import os
import pickle
import tempfile
import shutil

__all__ = ['Cache', 'CacheException', 'FailedToWriteCacheError', 'FailedToReadCacheError']


class CacheException(RuntimeError):
    def __init__(self, *args):
        super().__init__(*args)


class FailedToWriteCacheError(CacheException):
    """ Error thrown when the specified cache file can't be written. """
    def __init__(self, *args):
        super().__init__(*args)


class FailedToReadCacheError(CacheException):
    """ Error thrown when the specified cache file can't be read from. """
    def __init__(self, *args):
        super().__init__(*args)


class Cache:
    """ In 'with' statements: Saves and loads cached data initialized by a factory in the constructor. """
    def __init__(self, path: str, factory = None, write_on_exit=True):
        """ Initializes the cache.
        
        Arguments:
            :param path: Path to the cache file location.
            :param factory: Factory used to create the data if no cached data found at the specified path.
        """
        self.path = path
        self.factory = factory
        self.data = None
        self.write_on_exit = write_on_exit
    
    def write(self, path: str = None):
        """
        Writes the data to the cache file.
        Throws a FailedToWriteCacheError if the path points to a non-file.

        Arguments:
            :param path: Optional new path to
        """
        path = path or self.path
        if path is None:
            return
        if os.path.exists(path) and not os.path.isfile(path):
            raise FailedToWriteCacheError("Cache file %s can't be written to, because it exists but is not a file." % path)
        if not os.path.isdir(os.path.dirname(os.path.abspath(path))):
            os.makedirs(os.path.dirname(path))
        with tempfile.NamedTemporaryFile(delete=False) as tf:
            pickle.dump(self.data, tf)
            tf.flush()
            os.fsync(tf.fileno())
        shutil.move(tf.name, path)
        if self.path is None:
            self.path = path
    
    def load(self, path:str=None):
        """
        Attempts to load the data from the path, else creates new data using the provided factory method.
        Raises FailedToReachCacheError if the target file exists but is not a file.

        Arguments:
            :param path: Explicit path to cache file.
        """
        path = path or self.path
        # Always create data if no path is selected and there is no data yet
        if path is None and self.factory is not None:
            self.data = self.factory()
            return self.data
        # Else load from cache or create a new one
        if os.path.isfile(path):
            with open(path, 'rb') as file:
                self.data = pickle.load(file)
        elif os.path.exists(path):
            raise FailedToReadCacheError("Cache \"%s\" can't be loaded, because it exists but is not a file." % path)
        elif self.factory is not None:
            self.data = self.factory()
        if self.path is None:
            self.path = path
        return self.data
    
    def __enter__(self):
        self.load()
        return self

    def __exit__(self, *args, **kwargs):
        if self.write_on_exit:
            self.write()
