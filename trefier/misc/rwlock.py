from __future__ import annotations
from typing import Callable, Any
from functools import wraps
import threading

__author__ = "Mateusz Kobos"


__all__ = ['RWLock', 'async_reader', 'async_writer', 'ReaderLock', 'WriterLock']


class RWLock:
	"""Synchronization object used in a solution of so-called second 
	readers-writers problem. In this problem, many readers can simultaneously 
	access a share, and a writer has an exclusive access to this share.
	Additionally, the following constraints should be met: 
	1) no reader should be kept waiting if the share is currently opened for 
		reading unless a writer is also waiting for the share, 
	2) no writer should be kept waiting for the share longer than absolutely 
		necessary. 
	
	The implementation is based on [1, secs. 4.2.2, 4.2.6, 4.2.7] 
	with a modification -- adding an additional lock (C{self.__readers_queue})
	-- in accordance with [2].
		
	Sources:
	[1] A.B. Downey: "The little book of semaphores", Version 2.1.5, 2008
	[2] P.J. Courtois, F. Heymans, D.L. Parnas:
		"Concurrent Control with 'Readers' and 'Writers'", 
		Communications of the ACM, 1971 (via [3])
	[3] http://en.wikipedia.org/wiki/Readers-writers_problem
	"""
	
	def __init__(self):
		self.__read_switch = _LightSwitch()
		self.__write_switch = _LightSwitch()
		self.__no_readers = threading.Lock()
		self.__no_writers = threading.Lock()
		self.__readers_queue = threading.Lock()
		"""A lock giving an even higher priority to the writer in certain
		cases (see [2] for a discussion)"""
	
	def reader_acquire(self):
		self.__readers_queue.acquire()
		self.__no_readers.acquire()
		self.__read_switch.acquire(self.__no_writers)
		self.__no_readers.release()
		self.__readers_queue.release()
	
	def reader_release(self):
		self.__read_switch.release(self.__no_writers)
	
	def writer_acquire(self):
		self.__write_switch.acquire(self.__no_readers)
		self.__no_writers.acquire()
	
	def writer_release(self):
		self.__no_writers.release()
		self.__write_switch.release(self.__no_readers)

	def reader(self):
		return ReaderLock(self)

	def writer(self):
		return WriterLock(self)
	

class _LightSwitch:
	"""An auxiliary "light switch"-like object. The first thread turns on the 
	"switch", the last one turns it off (see [1, sec. 4.2.2] for details)."""
	def __init__(self):
		self.__counter = 0
		self.__mutex = threading.Lock()
	
	def acquire(self, lock):
		self.__mutex.acquire()
		self.__counter += 1
		if self.__counter == 1:
			lock.acquire()
		self.__mutex.release()

	def release(self, lock):
		self.__mutex.acquire()
		self.__counter -= 1
		if self.__counter == 0:
			lock.release()
		self.__mutex.release()


class ReaderLock:
	def __init__(self, rwlock: RWLock):
		self._rwlock = rwlock

	def __enter__(self):
		self._rwlock.reader_acquire()

	def __exit__(self, *args, **kwargs):
		self._rwlock.reader_release()


class WriterLock:
	def __init__(self, rwlock: RWLock):
		self._rwlock = rwlock

	def __enter__(self):
		self._rwlock.writer_acquire()

	def __exit__(self, *args, **kwargs):
		self._rwlock.writer_release()


def async_reader(get_lock: Callable[[Any], RWLock]):
	""" Decorator that uses a lock getter to lock the function call with a reader lock """
	def wrapper(f):
		@wraps(f)
		def wrapped(self, *args, **kwargs):
			with get_lock(self).reader():
				return f(self, *args, **kwargs)
		return wrapped
	return wrapper


def async_writer(get_lock: Callable[[Any], RWLock]):
	""" Decorator that uses a lock getter to lock the function call with a writer lock """
	def wrapper(f):
		@wraps(f)
		def wrapped(self, *args, **kwargs):
			with get_lock(self).writer():
				return f(self, *args, **kwargs)
		return wrapped
	return wrapper
