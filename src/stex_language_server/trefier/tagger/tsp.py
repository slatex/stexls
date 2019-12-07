''' Implementation of a simple "Tagger Server Protocol" '''

from __future__ import annotations
from typing import Any, List, Union, Optional
from enum import IntEnum


class Message:
    ' Generic message base class '
    pass


class RequestMessage(Message):
    ' A request between server and client. A request always requires a response message. '
    def __init__(self, json: str, id: Union[str, int], method: str, params: Union[List[Any], object] = None):
        super().__init__(json)
        self.id = id
        self.method = method
        self.params = params


class ResponseMessage(Message):
    ' A message in response to a request. Either result or error must be defined. Never both and never neither. '
    def __init__(self, json: str, id: Union[str, int, None], result: Any = None, error: Union[ResponseError, None] = None):
        super().__init__(json)
        self.id = id
        assert (result is not None) != (error is not None), 'Invalid response message structure: Either result or error must not be "None".'
        if result is not None:
            self.result = result
        if error is not None:
            self.error = error


class ResponseError:
    ' Container for error information used by ResponseMessage. '
    def __init__(self, code: ErrorCode, message: str, data: Union[Any, None] = None):
        super().__init__()
        self.code = code
        self.message = message
        if data is not None:
            self.data = data


class ErrorCode(IntEnum):
    ' Valid error codes. '
    ParseError = -2
    InvalidRequest = -3
    MethodNotFound = -4
    InvalidParams = -5
    InternalError = -6
    ServerNotInitialized = -7
    UnknownErrorCode = -8
    RequestCancelled = -9


class CancelParams:
    def __init__(self, id: Union[int, string]):
        super().__init__()
        self.id = id


class TaggingMethod(IntEnum):
    ''' Specifies the shape of generated tags and their contents.
    DISCRETE: Every location has 0 or 1 tags definetly attached to it.
    PROBABILISTIC: Every location has a probability for every tag attached to it.
    '''
    DISCRETE = 0
    PROBABILISTIC = 1
