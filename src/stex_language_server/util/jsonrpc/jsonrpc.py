from __future__ import annotations
from typing import Callable, Any, Optional, List, Dict, Union, Iterator
import functools
import threading
import traceback
import io
import select
import os
import logging
from ..promise import Promise
from .util import JsonRcpContentBuffer
from .util import parse
from .core import *

logger = logging.getLogger(__name__)

__all__ = ['request', 'notification', 'method', 'JsonRpcProtocol', 'JsonSerializable', 'JsonRpcError']

JsonSerializable = Union[List['JsonSerializable'], Dict[str, 'JsonSerializable'], str, int, float, bool, None]


class JsonRpcError(Exception):
    ' Exception raised by promises if the corresponding method returned an error. '
    pass


def request(method: str = None, block: bool = True):
    ''' Decorator that offloads the call to a json rpc server
        and blocks until the response has arrived.
        The function itself is NOT called. The function body should consist
        of only a "pass" statement.
    Parameters:
        method: The name under which the remote request will be sent.
    '''
    def decorator(f):
        @functools.wraps(f)
        def wrapper(self: JsonRpcProtocol, *args, **kwargs):
            if args and kwargs:
                raise ValueError('Mixing args and kwargs not allowed.')
            message = RequestMessage(self.generate_id(), method or f.__name__, args or kwargs)
            return self.send(message, as_batch=False, block=block)
        return wrapper
    return decorator

def notification(method: str = None):
    ''' Decorator that offloads the call to a json rpc server.
        Returns immediatly and no results or errors will be recoverable.
        The function itself is NOT called. The function body should consist
        of only a "pass" statement.
    Parameters:
        method: The name under which the remote notification will be sent.
    '''
    def decorator(f):
        @functools.wraps(f)
        def wrapper(self: JsonRpcProtocol, *args, **kwargs):
            if args and kwargs:
                raise ValueError('Mixing args and kwargs not allowed.')
            message = NotificationMessage(method or f.__name__, args or kwargs)
            self.send(message, as_batch=False)
        return wrapper
    return decorator

def method(name: str = None):
    ' Decorator that enables this function to be called remotely. '
    def decorator(f):
        f.jsonrpc_method_name = name or f.__name__
        return f
    return decorator

class JsonRpcProtocol:
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
        self.__next_id = 1
        self.__id_lock = threading.Lock()
        self.__write_lock = threading.Lock()
        self.connections = {}
    
    def connected(self, address: Any, rfile: io.BufferedReader, wfile: io.BufferedWriter):
        if address in self.connections:
            raise ValueError(f'Already connected to {address}')
        try:
            rfile.fileno()
        except:
            raise ValueError('rfile.fileno() not supported.')
        try:
            wfile.fileno()
        except:
            raise ValueError('wfile.fileno() not supported.')
        logger.info('connected to %s', address)
        rpipe, wpipe = os.pipe()
        with open(rpipe, 'rb', buffering=0) as private, open(wpipe, 'wb', buffering=0) as public:
            buffer = JsonRcpContentBuffer()
            pbuffer = JsonRcpContentBuffer()
            self.connections[address] = public
            try:
                while True:
                    rlist, _, _ = select.select([rfile, private], [], [], 10.0)
                    if not rlist:
                        continue
                    if rfile in rlist:
                        data = rfile.read(1024)
                        if not data:
                            raise EOFError()
                        for content in buffer.append(data):
                            logger.debug('<-- %s %s', address, content)
                            messages, is_batch, return_to_sender = parse(content)
                            responses = list(filter(None, map(self._handle_message, messages)))
                            if responses or return_to_sender:
                                self.send(*responses, *return_to_sender, as_batch=is_batch, target=wfile, block=False)
                    if private in rlist:
                        data = private.read(1024)
                        if not data:
                            continue
                        output = b''
                        for content, header in pbuffer.append(data, with_header=True):
                            logger.debug('<-- user %s', content)
                            output += header + content
                        if output:
                            logger.debug('--> %s', output)
                            wfile.write(output)
            finally:
                logger.info('disconnected from %s', address)
                del self.connections[address]

    def get_default_stream(self) -> io.BytesIO:
        return next(iter(self.connections.values()))
    
    def generate_id(self):
        with self.__id_lock:
            id = self.__next_id
            self.__next_id += 1
        return id

    def send(
        self,
        *messages: List[Message],
        target: io.BytesIO = None,
        as_batch: bool = True,
        block: bool = True) -> Optional[
            Union[JsonSerializable, List[JsonSerializable], Promise, List[Promise]]]:
        if as_batch:
            content = bytes('[' + ','.join(msg.serialize() for msg in messages) + ']', 'utf-8')
            header = bytes(f'content-length: {len(content)}\n\n', 'utf-8')
            data = header + content
        else:
            data = b''
            for msg in messages:
                content = bytes(msg.serialize(), 'utf-8')
                header = bytes(f'content-length: {len(content)}\n\n', 'utf-8')
                data += header + content
        
        promises = []
        for msg in messages:
            if isinstance(msg, RequestMessage):
                promise = Promise()
                promises.append(promise)
                with self.__promises_lock:
                    self.__promises[msg.id] = promise
        
        logger.debug('--> %s', data)
        with self.__write_lock:
            (target or self.get_default_stream()).write(data)

        if not promises:
            return

        if block:
            if len(promises) == 1 and not as_batch:
                # return ResponseMessage
                return promises[0].get()
            else:
                # return List[ResponseMessage]
                results = []
                for promise in promises:
                    try:
                        results.append(promise.get())
                    except JsonRpcError:
                        logger.warn('promise.get() in batch raised an exception and will be discarded.')
                return results
        else:
            if len(promises) == 1 and not as_batch:
                # return Promise
                return promises[0]
            else:
                # return List[Promise]
                return promises

    def call(
        self,
        method: str,
        params: Union[List[JsonSerializable], Dict[str, JsonSerializable]] = None) -> Any:
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

    def _handle_message(self, message: Message, throw_errors: bool = False) -> Optional[ResponseMessage]:
        ''' Takes a message and handles it according to it's type.
        cases:
            RequestMessage:
                Will be executed and a ResponseMessage with the result will be returned.
            NotificationMessage:
                Will be executed but nothing will be returned, even in an error case.
            ResponseMessage:
                Finds the promise with the corresponding id and resolves it with
                the response's value or makes it throw using the message.error object.
        Parameters:
            message: The incoming message to handle.
            throw_errors: Promises will throw error objects instead of resolving to them.
        Returns:
            ResponseMessage if input is a RequestMessage, else None will be returned.
        '''
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
                except:
                    traceback.print_exc()
        elif isinstance(message, ResponseMessage):
            if message.id in self.__promises:
                promise = self.__promises[message.id]
                if hasattr(message, 'result'):
                    promise.resolve(message.result)
                elif hasattr(message, 'error'):
                    if throw_errors:
                        promise.throw(JsonRpcError(message.error))
                    else:
                        promise.resolve(message.error)
                with self.__promises_lock:
                    del self.__promises[message.id]
        else:
            return ResponseMessage(
                None,
                error=ErrorObject(
                    ErrorCodes.InternalError,
                    data=f'Unknown message type: {type(message)}'))
