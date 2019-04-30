import os
import pickle
import tempfile
import shutil

class CacheException(RuntimeError):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

class FailedToWriteCacheError(CacheException):
    """ Error thrown when the specified cache file can't be written. """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

class FailedToReadCacheError(CacheException):
    """ Error thrown when the specified cache file can't be read from. """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

class InstanceCache:
    """ In 'with' statements: Loads a instance from cache or caches a new instanced created by a factory method. """
    
    def __init__(self, factory, path, write_on_exit=True):
        """ Initializes the cache.
        
        Arguments:
            :param factory: Factory used to create a new instance in case no cached instance was found.
            :param path: Path to the cache file location.
        """
        self.factory = factory
        self.path = path
        self.instance = None
        self.write_on_exit = write_on_exit
    
    def delete(self):
        """
        Deletes the cache if it exists, but throws if the cache is not a file.
        Does nothing if no cache at the path exists.
        Throws FailedToWriteCacheError if the path points to a non-file.
        """
        if self.path is None or not os.path.exists(self.path):
            return
        if not os.path.isfile(self.path):
            raise FailedToWriteCacheError("Can't delete cache at \"%s\", because it is not a file." % self.path)
        os.remove(self.path)
    
    def write(self, path:str=None):
        """
        Writes the instance to the cache file.
        Throws a FailedToWriteCacheError if the path points to a non-file.

        Arguments:
            :param path: Explicit path to cache file.
        """
        path = path or self.path
        if path is None:
            return
        if os.path.exists(path) and not os.path.isfile(path):
            raise FailedToWriteCacheError("Cache file %s can't be written to, because it exists but is not a file." % path)
        with tempfile.NamedTemporaryFile(dir=os.path.dirname(path), prefix='.', delete=False) as tf:
            pickle.dump(self.instance, tf)
            tf.flush()
            os.fsync(tf.fileno())
        shutil.move(tf.name, path)
    
    def load(self, path:str=None):
        """
        Attempts to load the instance from the path, else creates a new instance using the provided factory method.
        Raises FailedToReachCacheError if the target file exists but is not a file.

        Arguments:
            :param path: Explicit path to cache file.
        """
        path = path or self.path
        # Always create instance if no path is selected and there is no instance yet
        if path is None:
            self.instance = self.factory()
            return self.instance
        # Else load from cache or create a new one
        if os.path.isfile(path):
            with open(path, 'rb') as file:
                self.instance = pickle.load(file)
        elif os.path.exists(path):
            raise FailedToReadCacheError("Cache \"%s\" can't be loaded, because it exists but is not a file." % path)
        else:
            self.instance = self.factory()
        return self.instance
    
    def __enter__(self):
        self.load()
        return self

    def __exit__(self, *args, **kwargs):
        if self.write_on_exit:
            self.write()       
