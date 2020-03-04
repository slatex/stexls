from typing import Any, Tuple
import threading

__all__ = ['Promise']

class Promise:
    " Creates an container for a value that doesn't exist yet. "
    def __init__(self):
        self._event = threading.Event()
        self._lock = threading.Lock()

    def resolve(self, value: Any):
        ''' Gives the container a value and signals waiting threads the event.
            Raises ValueError if the promise resolved before. '''
        with self._lock:
            if self.has_resolved():
                raise ValueError('Promise already resolved.')
            self._value = value
            self._event.set()
    
    def throw(self, exception):
        ''' Resolves the promise but instead of a value it signals waiting threads
            that an exception should be thrown.
            Raises ValueError if the promise resolved before. '''
        with self._lock:
            if self.has_resolved():
                raise ValueError('Promise already resolved.')
            self._exception = exception
            self._event.set()
    
    def has_resolved(self) -> bool:
        ' Returns wether the promise was resolved or raised an exception. '
        return self._event.is_set()
    
    def has_raised_exception(self) -> bool:
        ' Returns true if the promise was resolved by throw(exception). '
        return self.has_resolved() and hasattr(self, '_exception')
    
    def has_value(self) -> bool:
        ' Returns true if the promise was resolved by resolve(value). '
        return self.has_resolved() and hasattr(self, '_value')
    
    def get(self, timeout: float = None) -> Any:
        ''' Blocks until the promise is resolved or the timeout runs out.
            If the promise resolved, then the value is returned.
            If a throw(exception) was called, the exception will be raised.
            If the timeout runs out a TimeoutError will be raise.
        Parameters:
            timeout: Time in seconds to wait. If "None" blocks indefinetly.
        Return:
            Returns the value provided from resolve(value) if called.
        '''
        if not self._event.wait(timeout):
            raise TimeoutError()
        if self.has_raised_exception():
            raise self._exception
        if self.has_resolved():
            return self._value
        raise RuntimeError('Invalid state: No value and no exception')
