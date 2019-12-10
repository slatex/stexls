from __future__ import annotations
from typing import Callable, Any, Optional, List, Dict
import itertools
import functools
import inspect
import threading
import json
import traceback
from .core import *

def request(method: str = None, target_getter: Callable[[JsonRpc], Any] = None):
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
            return self.submit_request(method or f.__name__, args, kwargs, target=target_getter(self) if target_getter else None)
        return wrapper
    return decorator

def notification(method: str = None, target_getter: Callable[[JsonRpc], Any] = None):
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
            self.submit_notification(method or f.__name__, args, kwargs, target=target_getter(self) if target_getter else None)
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
    
    def generate_id(self):
        ' Generates the next id. Threadsafe. '
        with self.__next_id_lock:
            id = self.__next_id
            self.__next_id += 1
        return id
    
    def submit_request(self, method: str, args, kwargs, target: Optional[Any] = None) -> Any:
        ' Creates a request object and sends it to the target. Blocks until send() is resolved. '
        if args and kwargs:
            raise ValueError('Mixing of args and kwargs is not allowed.')
        return self.send(RequestMessage(self.generate_id(), method, args or kwargs), target)

    def submit_notification(self, method: str, args, kwargs, target: Optional[Any] = None):
        ' Creates a notification object and sends it to the target. Returns immediately. '
        if args and kwargs:
            raise ValueError('Mixing of args and kwargs is not allowed')
        self.send(NotificationMessage(method, args or kwargs), target)

    def send(self, message: Union[Message, List[Message]], target: Optional[Any] = None) -> Optional[Any, List[Any]]:
        ''' Sends a message or a batch of messages to the target
            and blocks until all responses have been resolved.
        Parameters:
            message: A message or batch of messages to send to the target.
            target: An optional identifier for the target to send the message to.
        Returns:
            Response or list of responses from the target.
        '''
        raise NotImplementedError()
    
    def resolve(self, response: ResponseMessage):
        ' Resolves pending requests with the same id as the response. '
        raise NotImplementedError()

    def call(self, method: str, params: Union[List[Any], Dict[str, Any]]) -> Any:
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

    def handle(self, raw_message: str) -> Union[Message, List[Message]]:
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
            batch = []
            for ok, message in map(self.__restore_message(obj)):
                if ok:
                    response = self.__handle_message(message)
                    if response:
                        batch.append(response)
                else:
                    batch.append(response)
            response = batch
        else:
            ok, message = self.__restore_message(obj)
            if ok:
                response = self.__handle_message(message)
            else:
                response = message
        return response
    
    def __handle_message(self, message: Message) -> Optional[ResponseMessage]:
        ' A helper that creates response messages according to message type. '
        if isinstance(message, RequestMessage):
            if message.method not in self.methods:
                return ResponseMessage(message.id, error=METHOD_NOT_FOUND)
            try:
                params = message.params if hasattr(message, 'params') else None
                result = self.call(message.method, params)
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
                None,
                error=ErrorObject(
                    ErrorCodes.InternalError,
                    data=f'Unknown message type: {type(message)}'))

    def __restore_message(self, obj: object) -> Tuple[bool, Message]:
        ''' Parses the json object and attemps to restore the original Message object.
        Returns:
            Tuple of bool and Message.
            If the bool is True, then the message is the restored message.
            If the bool is False, then the message could not be restored
            or is in an illegal state, therefore an error response object is returned.
        '''
        protocol = obj.get('jsonrpc')
        if protocol is None or protocol != '2.0':
            return (False, INVALID_REQUEST)
        if 'result' in obj and 'error' in obj:
            return (False, INVALID_REQUEST)
        id = obj.get('id')
        if 'method' in obj:
            method = obj.get('method')
            params = obj.get('params')
            print(id, method, params)
            if 'params' in obj and params is None:
                return (False, INVALID_REQUEST)
            if 'id' in obj:
                return (True, RequestMessage(id, method, params))
            else:
                return (True, NotificationMessage(method, params))
        elif 'result' in obj:
            result = obj.get('result')
            if result is None:
                return (False, INVALID_REQUEST)
            return (True, ResponseMessage(id, result=result))
        elif 'error' in obj:
            error = obj.get('error')
            if error is None:
                return (False, INVALID_REQUEST)
            return (True, ResponseMessage(id, error=error))
        else:
            return (False, INVALID_REQUEST)