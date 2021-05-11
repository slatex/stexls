
from typing import Any


class JsonRpcException(Exception):
    ' Base for exceptions raised by this module. '

    def __init__(self, code: int, message: str = '', data: Any = None, *args: object) -> None:
        super().__init__(message, *args)
        self.code = code
        self.data = data

    def __int__(self): return self.code


class InternalErrorException(JsonRpcException):
    ' Exception raised when request returns with internal error. '

    def __init__(self, message: str = 'Internal error', *args: object) -> None:
        super().__init__(-32603, message, *args)


class InvalidParamsException(JsonRpcException):
    ' Exception raised when request returns with invalid params error. '

    def __init__(self, message: str = 'Invalid params', *args: object) -> None:
        super().__init__(-32602, message, *args)


class MethodNotFoundException(JsonRpcException):
    ' Exception raised when request calls an invalid method. '

    def __init__(self, message: str = 'Method not found', *args: object) -> None:
        super().__init__(-32601, message, *args)


class ParseErrorException(JsonRpcException):
    ' Exception raised when the message sent to a server is invalid json. '

    def __init__(self, message: str = 'Parse error', *args: object) -> None:
        super().__init__(-32700, message, *args)


class InvalidRequestException(JsonRpcException):
    ' Exceptinon raised when the message sent to a server is malformed. '

    def __init__(self, message: str = 'Invalid request', *args: object) -> None:
        super().__init__(-32600, message, *args)


class ServerErrorException(JsonRpcException):
    ' Exception raised for implementation reserved exceptions. '
