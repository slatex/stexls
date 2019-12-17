from __future__ import annotations
from typing import Union, Any, Awaitable
from collections import defaultdict
import asyncio
import functools
import logging
from .core import Message, NotificationMessage, RequestMessage, ResponseMessage, ErrorObject, ErrorCodes
log = logging.getLogger(__name__)

__all__ = ['request', 'notification', 'method', 'DispatcherBase', 'MessageHandler']

def alias(name: str):
    assert name is not None
    def alias_decorator(f):
        log.debug('JsonRpc hook alias %s->%s', f, name)
        f.json_rpc_name = name
        return f
    return alias_decorator

def request(f):
    log.debug('JsonRpc request hook: %s', f)
    if not hasattr(f, 'json_rpc_name'):
        f.json_rpc_name = f.__name__
    @functools.wraps(f)
    def request_wrapper(self: DispatcherBase, *args, **kwargs):
        if args and kwargs:
            raise ValueError('Mixing args and kwargs not allowed.')
        f(self, *args, **kwargs)
        return self.request(f.json_rpc_name, args or kwargs)
    return request_wrapper

def notification(f):
    log.debug('JsonRpc notification hook: %s', f)
    if not hasattr(f, 'json_rpc_name'):
        f.json_rpc_name = f.__name__
    @functools.wraps(f)
    def notification_wrapper(self: DispatcherBase, *args, **kwargs):
        if args and kwargs:
            raise ValueError('Mixing args and kwargs not allowed.')
        f(self, *args, **kwargs)
        return self.notification(f.json_rpc_name, args or kwargs)
    return notification_wrapper

def method(f):
    ' Decorator that enables this function to be called remotely. '
    log.debug('JsonRpc method hook: %s', f)
    if not hasattr(f, 'json_rpc_name'):
        f.json_rpc_name = f.__name__
    f.json_rpc_method = True
    return f


class DispatcherBase:
    def __init__(self):
        self.__methods = {}
        for attr in dir(self):
            if not attr.startswith('_'):
                val = getattr(self, attr)
                if callable(val) and hasattr(val, 'json_rpc_method') and val.json_rpc_method:
                    name = val.json_rpc_name
                    if name in self.__methods:
                        raise ValueError(f'Two or more methods with the name: {name}')
                    self.__methods[name] = val
                    log.debug('Registered dispatcher method %s as "%s".', val, name)
        self.__next_id = 1
        self.__requests = defaultdict(asyncio.Future)
        self.__targets = defaultdict(asyncio.Queue)
        self.__default_target = asyncio.Future()

    def __generate_id(self):
        id = self.__next_id
        self.__next_id += 1
        log.debug('Generated id %i.', id)
        return id
    
    async def request(self, method: str, params: Union[list, dict], target: Any = None) -> Any:
        log.info('Sending request for %s(%s) to %s.', method, params, target)
        message = RequestMessage(self.__generate_id(), method, params)
        await self.__targets[target or await self.__default_target].put(message)
        try:
            return await self.__requests[message.id]
        finally:
            log.debug('Finished waiting for response of request %s', message.id)
            del self.__requests[message.id]
    
    async def notification(self, method: str, params: Union[list, dict], target: Any = None) -> Any:
        log.info('Sending notification %s(%s) to %s', method, params, target)
        message = NotificationMessage(method, params)
        await self.__targets[target or await self.__default_target].put(message)

    def call(self, method: str, params: Union[list, dict, None], id: Union[int, str] = None) -> ResponseMessage:
        fn = self.__methods.get(method)
        if not fn:
            log.warning('Invalid method name "%s" called.', method)
            if id is None:
                return 
            return ResponseMessage(id, error=ErrorObject(ErrorCodes.MethodNotFound))
        try:
            log.info('%s(%s) called with id %s.', method, params, id)
            if params is None:
                result = fn()
            elif isinstance(params, list):
                result = fn(*params)
            elif isinstance(params, dict):
                result = fn(**params)
            else:
                raise TypeError('Invalid params type %s.' % type(params))
            if id is None:
                return
            return ResponseMessage(id, result=result)
        except TypeError:
            log.exception('Possible invalid param error when calling %s(%s)', method, params)
            if id is None:
                return
            return ResponseMessage(id, error=ErrorObject(ErrorCodes.InvalidParams))
        except Exception as e:
            log.exception('InternalError during method call of %s with id %s.', method, id)
            if id is None:
                return
            return ResponseMessage(
                id, error=ErrorObject(ErrorCodes.InternalError, data=str(e)))

    async def send_task(self, target: Any, outputs: asyncio.Queue):
        log.info('Starting dispatcher send_task to %s', target)
        if not self.__default_target.done():
            log.debug('Setting default target to %s.', target)
            self.__default_target.set_result(target)
        while True:
            log.debug('Waiting for a message to send to %s', target)
            message = await self.__targets[target].get()
            if message is None:
                log.info('Dispatcher send_task to %s terminated.', target)
                break
            log.debug('Sending %s to %s', message, target)
            await outputs.put(message)

    async def _execute_task(self, target: Any, message: Message):
        log.debug('Executing task message: %s', message)
        if isinstance(message, RequestMessage):
            log.debug('Executing request %s (%s).', message.id, message.method)
            params = getattr(message, 'params', None)
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, self.call, message.method, params, message.id)
            log.debug('Putting response %s in %s', response, self.__targets[target])
            await self.__targets[target].put(response)
        elif isinstance(message, NotificationMessage):
            log.debug('Executing notification %s.', message.method)
            params = getattr(message, 'params', None)
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, self.call, message.method, params)
        elif isinstance(message, ResponseMessage):
            log.debug('Received response %s.', message.id)
            if message.id is None:
                if hasattr(message, 'error'):
                    log.warning('JsonRpcError(%i): %s', message.error.code, message.error.message)
                else:
                    log.warning('Response without id from %s: %s', target, message.result)
            elif message.id not in self.__requests:
                log.warning('Received response for non-existend id %s.', message.id)
            elif hasattr(message, 'error'):
                log.warning('Resolving request %s with error (%s): %s.',
                    message.id, message.error.code, message.error.message)
                self.__requests[message.id].set_exception(Exception(message.error.message))
            else:
                log.info('Resolving request %s.', message.id)
                self.__requests[message.id].set_result(message.result)
        else:
            log.error('Invalid message type received: %s', type(message))

    async def receive_task(self, target: Any, inputs: asyncio.Queue):
        log.info('Starting dispatcher receive_task from %s.', target)
        if not self.__default_target.done():
            log.debug('Setting default target to %s.', target)
            self.__default_target.set_result(target)
        try:
            while True:
                log.debug('Waiting for a message from %s.', target)
                message = await inputs.get()
                if message is None:
                    log.info('Dispatcher receive_task terminator received from %s.',target)
                    break
                log.debug('Received message %s from %s.', message, target)
                asyncio.create_task(self._execute_task(target, message))
        finally:
            log.debug('Receive task finished, inserting terminator into send task.')
            await self.__targets[target].put(None)
            
    async def close(self):
        log.info('Stopping dispatcher.')
        self.__default_target.cancel()
        for target, q in self.__targets.items():
            log.debug('Terminating target %s', target)
            await q.put(None)
        for id, fut in self.__requests.items():
            log.debug('Canceling request future %s', id)
            fut.cancel()
        log.info('Dispatcher stopped.')