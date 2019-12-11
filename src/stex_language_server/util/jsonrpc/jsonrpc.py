from __future__ import annotations
from typing import Callable, Any, Optional, List, Dict
import itertools
import functools
import inspect
import threading
import json
import traceback
from .core import *

__all__ = ['request', 'notification', 'method', 'json2message', 'JsonRpc']

def request(method: str = None):
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
            return self.submit_request(method or f.__name__, args, kwargs)
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
            self.submit_notification(method or f.__name__, args, kwargs)
        return wrapper
    return decorator

def method(name: str = None):
    ' Decorator that enables this function to be called remotely. '
    def decorator(f):
        f.jsonrpc_method_name = name or f.__name__
        return f
    return decorator

def json2message(obj: object) -> Message:
    ''' Parses the json object and attemps to restore the original Message object.
    Returns:
        Returns the original message object or raises a ValueError
        if the json object is invalid.
    '''
    protocol = obj.get('jsonrpc')
    if protocol is None or protocol != '2.0':
        raise ValueError(f'Invalid protocol: {protocol}')
    if 'method' in obj and 'id' in obj and obj['id'] is None:
        raise ValueError('Request object must not have id "null".')
    if 'params' in obj and obj['params'] is None:
        raise ValueError('"params" must not be null.')
    if 'result' in obj and 'error' in obj:
        raise ValueError('"result" and "error" must not be present at the same time.')
    if 'error' in obj and obj['error'] is None:
        raise ValueError('"error" must not be null.')
    if 'result' in obj and obj['result'] is None:
        raise ValueError('"result" must not be null.')
    if 'method' in obj:
        method = obj.get('method')
        params = obj.get('params')
        if 'id' in obj:
            return RequestMessage(obj['id'], method, params)
        else:
            return NotificationMessage(method, params)
    elif 'result' in obj:
        result = obj.get('result')
        return ResponseMessage(obj.get('id'), result=result)
    elif 'error' in obj:
        error = obj.get('error')
        return ResponseMessage(obj.get('id'), error=error)
    else:
        raise ValueError('Unable to restore message.')


class JsonRpc:
    def __init__(self):
        self.methods = []
        for attr in dir(self):
            if not attr.startswith('_'):
                val = getattr(self, attr)
                if callable(val) and hasattr(val, 'jsonrpc_method_name'):
                    name = val.jsonrpc_method_name
                    if name in self.methods:
                        raise ValueError(f'Two or more methods with the name: {name}')
                    self.methods.append(name)
        self.__next_id = 1
        self.__next_id_lock = threading.Lock()

    def send(
        self,
        message: Union[Message, List[Message]],
        target: Any = None) -> Union[object, List[ResponseMessage], None]:
        ''' Sends a message or a batch of messages
            and blocks until all responses have been resolved.
            RequestMessages need to be resolveable using resolve().
        Parameters:
            message: A message or batch of messages to send.
        Returns:
            Result of a request if the message was a request.
            Raises exception if the message was a request and failed.
            Returns list of ResponseMessage if the message was a batch
            regardless of if the request failed or not.
            Returns None if the message was not a request or if 
            not request was inside the batch.
        '''
        raise NotImplementedError()

    def resolve(self, response: ResponseMessage):
        ' Resolves pending requests with the same id as the response. '
        raise NotImplementedError()
    
    def generate_id(self):
        ' Generates the next id. Threadsafe. '
        with self.__next_id_lock:
            id = self.__next_id
            self.__next_id += 1
        return id
    
    def submit_request(self, method: str, args, kwargs, target: Any = None) -> object:
        ' Creates a request object and sends it. Returns the result or raises if the request failed. '
        if args and kwargs:
            raise ValueError('Mixing of args and kwargs is not allowed.')
        return self.send(RequestMessage(self.generate_id(), method, args or kwargs), target=target)

    def submit_notification(self, method: str, args, kwargs, target: Any = None):
        ' Creates a notification object and sends it. Returns the result of send(). Returns immediately. '
        if args and kwargs:
            raise ValueError('Mixing of args and kwargs is not allowed')
        return self.send(NotificationMessage(method, args or kwargs), target=target)

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
            return getattr(self, method)()
        if isinstance(params, (list, tuple)):
            return getattr(self, method)(*params)
        if isinstance(params, dict):
            return getattr(self, method)(**params)
        else:
            raise ValueError(f'Invalid params type: {type(params)}')

    def receive(self, raw_message: str) -> Union[Message, List[Message]]:
        ''' Handles a still serialized message received from the server
            or a client. The message is desierialized and exececuted
            if it is a request or notification. The request response
            message is returned and needs to be send to the partner.
        Parameters:
            raw_message: A raw message from client or server.
        Returns:
            A response or batch of responses that need to be send.
        '''
        try:
            obj = json.loads(raw_message)
        except json.JSONDecodeError:
            return PARSE_ERROR
        if isinstance(obj, list):
            response = []
            for raw in obj:
                try:
                    message = json2message(raw)
                    response_message = self.__handle_message(message)
                except ValueError:
                    response_message = INVALID_REQUEST
                if response_message is not None:
                    response.append(response_message)
        else:
            try:
                message = json2message(obj)
                response = self.__handle_message(message)
            except ValueError:
                response = INVALID_REQUEST
        return response
    
    def __handle_message(self, message: Message) -> Optional[ResponseMessage]:
        ' A helper that creates response messages according to message type. '
        if isinstance(message, RequestMessage):
            if message.method not in self.methods:
                return ResponseMessage(message.id, error=METHOD_NOT_FOUND)
            try:
                if hasattr(message.params):
                    result = self.call(message.method, message.params)
                else:
                    result = self.call(message.method)
            except TypeError:
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
                    traceback.print_exec()
        elif isinstance(message, ResponseMessage):
            self.resolve(message)
        else:
            return ResponseMessage(
                error=ErrorObject(
                    ErrorCodes.InternalError,
                    data=f'Unknown message type: {type(message)}'))
