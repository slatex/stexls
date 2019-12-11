from __future__ import annotations
from typing import Callable, Any, Optional, List, Dict, Union
import itertools
import functools
import inspect
import threading
import json
import traceback
import io
import socketserver
import socket
from ..buffer import ByteBuffer
from ..promise import Promise
from .util import JsonRcpContentBuffer
from .util import json2message
from .core import *

__all__ = ['request', 'notification', 'method', 'JsonRpc']

def request(method: str = None, block: bool = True):
    ''' Decorator that offloads the call to a JsonRpc server
        and blocks until the response has arrived.
        The function itself is NOT called. The function body should consist
        of only a "pass" statement.
    Parameters:
        method: The name under which the remote request will be sent.
    '''
    def decorator(f):
        @functools.wraps(f)
        def wrapper(self: JsonRpc, *args, **kwargs):
            if args and kwargs:
                raise ValueError('Mixing args and kwargs not allowed.')
            message = RequestMessage(self.generate_id(), method or f.__name__, args or kwargs)
            return self.send(message, block=block)
        return wrapper
    return decorator

def notification(method: str = None):
    ''' Decorator that offloads the call to a JsonRpc server.
        Returns immediatly and no results or errors will be recoverable.
        The function itself is NOT called. The function body should consist
        of only a "pass" statement.
    Parameters:
        method: The name under which the remote notification will be sent.
    '''
    def decorator(f):
        @functools.wraps(f)
        def wrapper(self: JsonRpc, *args, **kwargs):
            if args and kwargs:
                raise ValueError('Mixing args and kwargs not allowed.')
            message = NotificationMessage(method or f.__name__, args or kwargs)
            self.send(message)
        return wrapper
    return decorator

def method(name: str = None):
    ' Decorator that enables this function to be called remotely. '
    def decorator(f):
        f.jsonrpc_method_name = name or f.__name__
        return f
    return decorator

class JsonRpc:
    def __init__(self):
        self.methods = {}
        for attr in dir(self):
            if not attr.startswith('_'):
                val = getattr(self, attr)
                if callable(val) and hasattr(val, 'jsonrpc_method_name'):
                    name = val.jsonrpc_method_name
                    if name in self.methods:
                        raise ValueError(f'Two or more methods with the name: {name}')
                    self.methods[name] = val
        self.__promises = {}
        self.__promises_lock = threading.Lock()
        self.__writer_lock = threading.Lock()
        self.__next_id = 1
        self.__id_lock = threading.Lock()

    def get_default_target(self) -> io.BytesIO:
        raise NotImplementedError()
    
    def generate_id(self):
        with self.__id_lock:
            id = self.__next_id
            self.__next_id += 1
        return id

    def send(
        self,
        message_or_batch: Union[Message, List[Message]],
        target: io.BytesIO = None,
        block: bool = True) -> Optional[ResponseMessage, List[ResponseMessage]]:
        if isinstance(message_or_batch, Message):
            serialized = message_or_batch.serialize()
            if isinstance(message_or_batch, RequestMessage):
                promise = Promise()
                with self.__promises_lock:
                    self.__promises[message_or_batch.id] = promise
        else:
            serialized = '[' + ','.join(msg.serialize() for msg in message_or_batch) + ']'
            promises = []
            for msg in message_or_batch:
                if isinstance(msg, RequestMessage):
                    promise = Promise()
                    promises.append(promise)
                    with self.__promises_lock:
                        self.__promises[msg.id] = promise
        data = bytes(serialized, 'utf-8')
        header = bytes(f'content-length: {len(data)}\n\n', 'utf-8')
        stream = target or self.get_default_target()
        with self.__writer_lock:
            count = stream.write(header)
            count += stream.write(data)
        if count != len(data) + len(header):
            raise ValueError('Stream failed to write all bytes.')
        if isinstance(message_or_batch, RequestMessage):
            if block:
                return promise.get()
            else:
                return promise
        elif isinstance(message_or_batch, list):
            if block:
                return [
                    promise.get()
                    for promise in promises
                ]
            else:
                return promises
        return None

    def call(self, method: str, params: Union[List[Any], Dict[str, Any]] = None) -> Any:
        ''' Executes <method> by applying <params> and returns the methods return value.
        Parameters:
            method: Method identifier.
            params: Parameters for the method. "None", [], () or {} to not apply any parameters.
        Returns:
            Return value of the method.
        '''
        if method not in self.methods:
            raise ValueError(f'Unknown method: {method}')
        if params is None:
            return self.methods[method]()
        if isinstance(params, (list, tuple)):
            return self.methods[method](*params)
        if isinstance(params, dict):
            return self.methods[method](**params)
        else:
            raise ValueError(f'Invalid params type: {type(params)}')

    def receive(self, raw_message: str) -> Union[Message, List[Message]]:
        try:
            obj = json.loads(raw_message)
        except json.JSONDecodeError:
            return PARSE_ERROR
        if not isinstance(obj, (list, dict)):
            return INVALID_REQUEST
        if isinstance(obj, list):
            responses = []
            for raw in obj:
                try:
                    message = json2message(raw)
                    response = self.__handle_message(message)
                except ValueError:
                    response = INVALID_REQUEST
                except:
                    response = INTERNAL_ERROR
                if response is not None:
                    responses.append(response)
            return responses
        else:
            try:
                message = json2message(obj)
                return self.__handle_message(message)
            except ValueError:
                return INVALID_REQUEST
            except:
                return INTERNAL_ERROR
    
    def __handle_message(self, message: Message) -> Optional[ResponseMessage]:
        ' A helper that creates response messages according to message type. '
        if isinstance(message, RequestMessage):
            if message.method not in self.methods:
                return ResponseMessage(message.id, error=METHOD_NOT_FOUND)
            try:
                if hasattr(message, 'params'):
                    result = self.call(message.method, message.params)
                else:
                    result = self.call(message.method)
            except TypeError as e:
                return ResponseMessage(message.id, error=INVALIDA_PARAMS)
            except Exception as e:
                return ResponseMessage(message.id, error=ErrorObject(
                    ErrorCodes.InternalError, data=str(e)))
            return ResponseMessage(message.id, result=result)
        elif isinstance(message, NotificationMessage):
            if message.method in self.methods:
                try:
                    self.call(message.method, message.params)
                except Exception:
                    pass
        elif isinstance(message, ResponseMessage):
            if message.id in self.__promises:
                self.__promises[message.id].resolve(message)
                with self.__promises_lock:
                    del self.__promises[message.id]
        else:
            return ResponseMessage(
                None,
                error=ErrorObject(
                    ErrorCodes.InternalError,
                    data=f'Unknown message type: {type(message)}'))

