from __future__ import annotations
from typing import Callable, Any
import threading
import sys

class Future:
    def __init__(self, task: Callable[[], Any], response_timeout: float = 1.0):
        """ Creates a thread for the provided task.
            The return value can be retrieved by registering a callback using Future.done()
        :param task: Callable that returns something
        :param response_timeout: Maximum time the return value or raised exception waits until a warning is printed
        """
        self._response_timeout = response_timeout
        self._finished = threading.Event()
        self._return_value = None
        self._return_value_handled = threading.Event()
        self._did_raise_exception = False
        self._exception = None
        self._exception_handled = threading.Event()
        self._task_thread = threading.Thread(target=self._task_container, args=(task,))
        self._task_thread.start()
    
    def done(self, callback: Callable[[Any], None], catch: Optional[Callable[[Exception], None]] = None):
        """ Registers a callback for the return value and a callback for raised exceptions
        :param callback: A callback that expects a single argument,
            that is set to the return value of the task if it returns
        :param catch: A callback wich expects the an exception as argument and is thrown in case
            the task raises an exception.
        """
        assert callback is not None
        callback_thread = threading.Thread(
            target=self._callback_container,
            args=(callback, catch))
        callback_thread.start()
    
    def _task_container(self, task):
        try:
            self._return_value = task()
        except Exception as e:
            self._did_raise_exception = True
            self._exception = e
        self._notify()
    
    def _notify(self):
        self._finished.set()
        if self._response_timeout is not None:
            if self._did_raise_exception:
                if not self._exception_handled.wait(self._response_timeout):
                    print(f"Exception of future not handled withing {self._response_timeout} second", file=sys.stderr)
                    print(self._exception, file=sys.stderr)
            else:
                if not self._return_value_handled.wait(self._response_timeout):
                    print(f"Return value of future not handled within {self._response_timeout} second", file=sys.stderr)
    
    def _callback_container(self, callback, catch):
        self._finished.wait()
        try:
            if self._did_raise_exception:
                if catch is not None:
                    self._exception_handled.set()
                    catch(self._exception)
            else:
                self._return_value_handled.set()
                callback(self._return_value)
        except Exception as e:
            print("Exception thrown inside future callback", file=sys.stderr)
            print(e, file=sys.stderr)
