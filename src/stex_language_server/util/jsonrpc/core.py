""" This module implements jsonrpc 2.0 and other related utilities.
Specification from: https://www.jsonrpc.org/specification#overview
"""
from __future__ import annotations
from typing import Optional, Union, List, Dict, Any, Iterator, Iterable
import json
import functools
import itertools
from enum import IntEnum

from .util import validate_json, restore_message

__all__ = [
    'MessageObject',
    'RequestObject',
    'NotificationObject',
    'ResponseObject',
    'ErrorObject',
    'ErrorCodes'
]

class MessageObject:
    ' Base message. All Messages contain the string "jsonrpc: 2.0". '
    def __init__(self):
        self.jsonrpc = "2.0"


class RequestObject(MessageObject):
    ''' Request messages send a method
        with parameters to the sever.
        The server must repond with a ResponseObject containing
        the same id the client provided.
    '''
    def __init__(self, id: Union[str, int], method: str, params: Union[Dict[str, Any], List[Any]] = None):
        ''' Initializes the request object.
        Parameters:
            id: Client defined identifier used to re-identify the response.
            method: Remote procedure name to be executed on the server.
            params: Parameters for the method. Must be json serializable.
        '''
        super().__init__()
        if id is None:
            raise ValueError('RequestObject id must not be "None"')
        if not (params is None or isinstance(params, (dict, list, tuple))):
            raise ValueError(f'Invalid params type, allowed are list, dict and None: {type(params)}')
        self.id = id
        self.method = method
        if params is not None:
            self.params = params


class NotificationObject(MessageObject):
    ''' A notification is a request without an id.
        The server will try to execute the method but the client will not be notified
        about the results or errors.
    '''
    def __init__(self, method: str, params: Union[Dict[str, Any], List[Any]]):
        ''' Initializes a notification message.
            See RequestObject for information about parameters.
        '''
        super().__init__()
        self.method = method
        if params is not None:
            self.params = params


class ResponseObject(MessageObject):
    ''' A response message gives success or failure status in response
        to a request message with the same id.
    '''
    def __init__(
        self, id: Optional[Union[str, int]], result: Optional[Any] = None, error: Optional[ErrorObject] = None):
        ''' Initializes a response message.
        Parameters:
            id: The id of the request to respond to. "None" if there was an error detecting the request id.
            result: Result of the method execution.
                Result object should be json serializable.
                This must be "None" if the method failed.
            error: Information about method failure.
                This must be "None" if the method succeeded.
        '''
        super().__init__()
        if result is not None and error is not None:
            raise ValueError('Only either result or either error can be defined.')
        if error is not None:
            self.error = error
        else:
            self.result = result
        self.id = id


class ErrorObject:
    " Gives more information in case a request method can't be executed by the server. "
    def __init__(self, code: int, message: Optional[str] = None, data: Optional[Any] = None):
        ''' Constructs error object.
        Parameters:
            code: A number that indicates the error type occured.
                Error codes in range -32768 to -32000 are reserved by jsonrpc.
            message: A short description of the error.
            data: A primitive or structured value that contains additional information.
        '''
        self.code = code
        self.message = message or ErrorCodes.message(code)
        if data is not None:
            self.data = data
    

class ErrorCodes(IntEnum):
    ' jsonrpc reserved error codes '
    ParseError = -32700
    InvalidRequest = -32600
    MethodNotFound = -32601
    InvalidParams = -32602
    InternalError = -32603
    # (implementation defined)
    # ServerError = range(-32000, -32100)

    @staticmethod
    def message(code: int) -> Union[str, None]:
        if code == ErrorCodes.ParseError:
            return 'Parse error'
        if code == ErrorCodes.InvalidRequest:
            return 'Invalid Request'
        if code == ErrorCodes.MethodNotFound:
            return 'Method not found'
        if code == ErrorCodes.InvalidParams:
            return 'Invalid params'
        if code == ErrorCodes.InternalError:
            return 'Internal error'
        if code in range(-32000, -32100):
            return 'Server error'
        raise ValueError(f'Unknown error code: {code}')


class JsonRpcMessage:
    ''' This class represents a message in transit.
        A message can be a list of jrpc objects,
        but it also can just be a single jrpc object.
        The message can be built by adding requests,
        notifications an responses. After that it
        can be serialized using to_json and sent
        using any transmissin protocol.
        The target can then deserialize the message
        using from_json. All requests, notifications and responses
        in the given string will be placed accordingly and erros,
        if any occured during deserialization,
        can be queried using the errors() getter.
    '''
    def __init__(self, objects: Iterable[MessageObject] = (), is_batch: bool = False, errors: Iterable[ResponseObject] = ()):
        ' Initializes the message by storing the given objects. '
        self._requests = tuple(
            o for o in objects if isinstance(o, RequestObject))
        self._notifications = tuple(
            o for o in objects if isinstance(o, NotificationObject))
        self._responses = tuple(
            o for o in objects if isinstance(o, ResponseObject))
        self._errors = tuple(errors)
        self._is_batch = is_batch

    def requests(self) -> Iterable[RequestObject]:
        ' Iterable of requests in this message. '
        return self._requests

    def notifications(self) -> Iterable[NotificationObject]:
        ' Iterable of notifications in this message. '
        return self._notifications

    def responses(self) -> Iterable[ResponseObject]:
        ' Iterable of responses in this message. '
        return self._responses

    def errors(self) -> Iterable[ResponseObject]:
        ''' List of errors that occured or were detected while parsing this message. 
            These errors must be send back to the origin. '''
        return self._errors

    def is_batch(self) -> bool:
        ' Gets the internal flag of whether the objects form a single batch or not. '
        return self._is_batch

    @staticmethod
    def from_json(self, string: str) -> JsonRpcMessage:
        ' Deserializes the json string. '
        try:
            message = json.loads(string)
        except json.JSONDecodeError as e:
            err = ResponseObject(None, error=ErrorObject(ErrorCodes.InvalidRequest, data=str(e)))
            return JsonRpcMessage(errors=(err,))
        if not isinstance(message, (dict, list)):
            err = ResponseObject(None, error=ErrorObject(ErrorCodes.InvalidRequest, data=str(e)))
            return JsonRpcMessage(errors=(err,))
        if isinstance(message, dict):
            invalid = validate_json(message)
            if invalid is not None:
                return JsonRpcMessage(errors=(invalid,))
            restored = restore_message(message)
            return JsonRpcMessage(objects=(restored,))
        elif isinstance(message, list):
            errors = []
            objects = []
            for msg in message:
                invalid = validate_json(msg)
                if invalid is not None:
                    errors.append(invalid)
                else:
                    objects.append(restore_message(msg))
            return JsonRpcMessage(
                objects=objects, is_batch=True, errors=errors)

    def to_json(self) -> Iterator[str]:
        ''' Serializes all messages as json strings and yields
            the serialized strings for every message.
            If is_batch() is True, yields a single string with an
            json array that contains all serialized messages. '''
        serializations = (
            json.dumps(msg, default=lambda x: x.__dict__)
            for msg in itertools.chain(
                self.requests(), self.notifications(), self.responses()))
        if self.is_batch():
            yield '[' + ','.join(serializations) + ']'
        else:
            yield from serializations
