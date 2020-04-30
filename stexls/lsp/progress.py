from typing import Iterable, Callable, Awaitable, Optional
import asyncio

__all__ = ['ProgressTracker']

class ProgressTracker:
    def __init__(self):
        self.i = None
        self._it = None
        self.done = asyncio.Event()

    def __len__(self) -> Optional[int]:
        if hasattr(self._it, '__len__'):
            return len(self._it)
        return None

    def __call__(self, it: Iterable) -> Iterable:
        self._it = it
        for self.i, el in enumerate(it):
            yield el
        self.done = True

    async def on_progress(self, callback: Callable[[int, Optional[int], bool], Awaitable[None]], freq: float = 1.0):
        ''' Register an on progress coroutine, called every freq seconds.

        Parameters:
            callback: A coroutine called with the current element index, optional length of the iterator and a done flag, that is true after the iterator has finished.
            freq: callback sample frequency in seconds.
        
        Returns:
            None after the iterator finished.
        '''
        while not self.done.is_set():
            await asyncio.sleep(freq)
            await callback(self.i, len(self), self.done)
