""" This module implements jsonrpc 2.0 and other related utilities.
Specification from: https://www.jsonrpc.org/specification#overview
"""
from __future__ import annotations
from typing import Optional, Union, List, Dict, Any, Tuple
import traceback
import json
import queue
import threading
import functools
from enum import IntEnum

__all__ = [
    'Message',
    'RequestMessage',
    'NotificationMessage',
    'ResponseMessage',
    'validate_json',
    'RestoreException',
    'restore_message',
    'ErrorObject',
    'ErrorCodes',
    'PARSE_ERROR',
    'INVALID_REQUEST',
    'METHOD_NOT_FOUND',
    'INVALIDA_PARAMS',
    'INTERNAL_ERROR',
]

class Message:
    ' Base message. All Messages contain the string "jsonrpc: 2.0". '
    def __init__(self):
        self.jsonrpc = "2.0"
    
    def serialize(self, encoder: Optional[json.JSONEncoder] = None) -> str:
        ''' Serializes the message object into json.
        Parameters:
            encoder: Custom encoder in case method parameters are not serializable.
        Returns:
            JSON string.
        '''
        if encoder is None:
            return json.dumps(self, default=lambda o: o.__dict__)
        else:
            return encoder.encode(self.__dict__)


class RequestMessage(Message):
    ''' Request messages send a method
        with parameters to the sever.
        The server must repond with a ResponseMessage containing
        the same id the client provided.
    '''
    def __init__(self, id: Union[str, int], method: str, params: Union[Dict[str, Any], List[Any]] = None):
        ''' Initializes the request object.
        Parameters:
            id: Client defined identifier used to re-identify the response.
            method: Method to be performed by the server.
            params: Parameters for the method.
                The parameters must be in the right order if they are a list,
                or with the correct parameter names if a dictionary.
                The parameters should be json serializable, but you
                can use a custom JSONEncoder in Message.serialize().
        '''
        super().__init__()
        if id is None:
            raise ValueError('RequestMessage id must not be "None"')
        if not (params is None or isinstance(params, (dict, list, tuple))):
            raise ValueError(f'Invalid params type, allowed are list, dict and None: {type(params)}')
        self.id = id
        self.method = method
        if params is not None:
            self.params = params


class NotificationMessage(Message):
    ''' A notification is a request without an id.
        The server will try to execute the method but the client will not be notified
        about the results.
    '''
    def __init__(self, method: str, params: Union[Dict[str, Any], List[Any]]):
        ''' Initializes a notification message.
            See RequestMessage for information about parameters.
        '''
        super().__init__()
        self.method = method
        self.params = params


class ResponseMessage(Message):
    ''' A response message gives success or failure status in response
        to a request message with the same id.
    '''
    def __init__(
        self, id: Optional[Union[str, int]], result: Optional[Any] = None, error: Optional[ErrorObject] = None):
        ''' Initializes a response message.
        Parameters:
            id: The id of the request to respond to. "None" if there was an error detecting the request id.
            result: Result of the method execution.
                Result object should be json serializable or use a custom json encoder.
                This must be "None" if the method failed.
            error: Information about method failure. This must be "None" if the method succeeded.
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


PARSE_ERROR = ResponseMessage(None, error=ErrorObject(ErrorCodes.ParseError))
INVALID_REQUEST = ResponseMessage(None, error=ErrorObject(ErrorCodes.InvalidRequest))
METHOD_NOT_FOUND = ErrorObject(ErrorCodes.MethodNotFound)
INVALIDA_PARAMS = ErrorObject(ErrorCodes.InvalidParams)
INTERNAL_ERROR = ErrorObject(ErrorCodes.InternalError)
