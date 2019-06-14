from __future__ import annotations
from typing import Callable, Any, List
import threading
import sys
import traceback

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
        self._traceback: traceback.TracebackType = None
        self._exception_handled = threading.Event()
        self._callback_threads: List[threading.Thread] = []
        self._lock = threading.RLock()
        self._closed = False
        self._task_thread = threading.Thread(target=self._task_container, args=(task,))
        self._task_thread.start()

    def close(self):
        """ Closes the future and causes it to not accept any more callbacks """
        with self._lock:
            self._closed = True

    def join(self):
        """ Waits until all callbacks have been resolved """
        with self._lock:
            while self._callback_threads:
                thread = self._callback_threads.pop()
                thread.join()
    
    def done(self,
             callback: Callable[[Any], None],
             catch: Optional[Callable[[Any], None]] = None):
        """ Registers a callback for the return value and a callback for raised exceptions
        :param callback: A callback that expects a single argument,
            that is set to the return value of the task if it returns
        :param catch: A callback wich accepts a traceback as argument and is called in case the task raises an exception
        :returns self
        """
        if not callback:
            raise ValueError("callback may not be None")
        with self._lock:
            if self._closed:
                raise Exception("This future object is closed and does not accept any more callbacks")
            callback_thread = threading.Thread(
                target=self._callback_container,
                args=(callback, catch))
            self._callback_threads.append(callback_thread)
            callback_thread.start()
            return self

    def then(self, callback, catch):
        with self._lock:
            event = threading.Event()
            result_ptr = [None]
            traceback_ptr = [None]

            def _resolve_task(result):
                result_ptr[0] = result
                event.set()

            def _catch_task(tb):
                traceback_ptr[0] = tb
                event.set()

            self.done(_resolve_task, _catch_task)

            def _wait_task():
                event.wait()
                if traceback_ptr[0] is not None:
                    raise Exception(traceback_ptr[0])
                return result_ptr[0]

            thenable = Future(_wait_task)
            thenable.done(callback, catch)

            return thenable

    def _task_container(self, task):
        """ Contains the provided task and notifies all registered callbacks. """
        try:
            self._return_value = task()
        except:
            self._did_raise_exception = True
            self._traceback = traceback.format_exc()
        self._notify()
    
    def _notify(self):
        """ Notifies all callbacks that the task returned or raised an exception """
        self._finished.set()
        if self._response_timeout is not None:
            if self._did_raise_exception:
                if not self._exception_handled.wait(self._response_timeout):
                    print(self._traceback)
                    print(f"Exception of future not handled withing {self._response_timeout} second", file=sys.stderr)
            else:
                if not self._return_value_handled.wait(self._response_timeout):
                    print(f"Return value of future not handled within {self._response_timeout} second", file=sys.stderr)
    
    def _callback_container(self, callback, catch):
        """ Thread added by every callback and executed after the task resolves or throws. """
        self._finished.wait()
        try:
            if self._did_raise_exception:
                if catch is not None:
                    self._exception_handled.set()
                    catch(self._traceback)
            else:
                self._return_value_handled.set()
                callback(self._return_value)
        except:
            traceback.print_exc()
            if self._did_raise_exception:
                print("Exception thrown inside future catch()", file=sys.stderr)
            else:
                print("Exception thrown inside future callback()", file=sys.stderr)


def make_async(f):
    """ Decorator that wraps the function to always return a future object. """
    def wrapper(*args, **kwargs):
        return Future(lambda: f(*args, **kwargs))
    return wrapper
