from __future__ import annotations
from typing import List
import asyncio
import functools
import threading
import logging
from .core import *

log = logging.getLogger(__name__)

__all__ = ['request', 'notification', 'method', 'DispatcherBase', 'MessageTargetHandler']

def alias(name: str):
    def alias_decorator(f):
        log.debug('Dispatcher alias %s->%s', f.__name__, name)
        if hasattr(f, 'json_rpc_request_name'):
            f.json_rpc_request_name = name
        elif hasattr(f, 'json_rpc_notification_name'):
            f.json_rpc_notification_name = name
        elif hasattr(f, 'json_rpc_method_name'):
            f.json_rpc_method_name = name
        else:
            raise ValueError('Unable to alias function that is not a request, notification or method.')
        return f
    return alias_decorator

def request(f):
    log.debug('')
    if not hasattr(f, 'json_rpc_request_name'):
        f.json_rpc_request_name = f.__name__
    @functools.wraps(f)
    def request_wrapper(self: DispatcherBase, *args, **kwargs):
        if args and kwargs:
            raise ValueError('Mixing args and kwargs not allowed.')
        f(self, *args, **kwargs)
        return self.request(f.json_rpc_request_name, args or kwargs)
    return request_wrapper

def notification(f):
    if not hasattr(f, 'json_rpc_notification_name'):
        f.json_rpc_notification_name = f.__name__
    @functools.wraps(f)
    def notification_wrapper(self: DispatcherBase, *args, **kwargs):
        if args and kwargs:
            raise ValueError('Mixing args and kwargs not allowed.')
        f(self, *args, **kwargs)
        return self.notification(f.json_rpc_notification_name, args or kwargs)
    return notification_wrapper

def method(f):
    ' Decorator that enables this function to be called remotely. '
    if not hasattr(f, 'json_rpc_method_name'):
        f.json_rpc_method_name = f.__name__
    return f


class MessageTargetHandler:
    def receive(self, *message: Message):
        raise NotImplementedError()


class DispatcherBase:
    def __init__(self, target: MessageTargetHandler):
        self.__target = target
        self.__methods = {}
        for attr in dir(self):
            if not attr.startswith('_'):
                val = getattr(self, attr)
                if callable(val) and hasattr(val, 'jsonrpc_method_name'):
                    name = val.jsonrpc_method_name
                    if name in self.__methods:
                        raise ValueError(f'Two or more methods with the name: {name}')
                    self.__methods[name] = val
        self.__next_id = 1
        self.__id_lock = threading.Lock()

    def __generate_id(self):
        with self.__id_lock:
            id = self.__next_id
            self.__next_id += 1
        return id
    
    def request(self, method: str, params: Union[list, dict]) -> Any:
        message = RequestMessage(self.__generate_id(), method, params)
        return self.send(message)
    
    def notification(self, method: str, params: Union[list, dict]) -> Any:
        message = NotificationMessage(method, params)
        return self.send(message)
    
    async def send(self, *message: Message, as_batch: bool = True):
        return await self.__target.receive(*message)
    
    def call(self, method: str, params: Union[list, dict, None], id: Union[int, str] = None) -> ResponseMessage:
        fn = self.__methods.get(method)
        if not fn:
            return ResponseMessage(id, error=ErrorObject(ErrorCodes.MethodNotFound))
        try:
            if params is None:
                result = fn()
            elif isinstance(params, list):
                result = fn(*params)
            elif isinstance(params, dict):
                result = fn(**params)
        except TypeError:
            return ResponseMessage(id, error=ErrorObject(ErrorCodes.InvalidParams))
        return ResponseMessage(id, result=result)
