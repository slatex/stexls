
class JsonRpcException(Exception):
    ' Base for exceptions raised by this module. '

class InternalErrorException(JsonRpcException):
    ' Exception raised when request returns with internal error. '

class InvalidParamsException(JsonRpcException):
    ' Exception raised when request returns with invalid params error. '

class MethodNotFoundException(JsonRpcException):
    ' Exception raised when request calls an invalid method. '

class ParseErrorException(JsonRpcException):
    ' Exception raised when the message sent to a server is invalid json. '

class InvalidRequestException(JsonRpcException):
    ' Exceptinon raised when the message sent to a server is malformed. '

class ServerErrorException(JsonRpcException):
    ' Exception raised when the type of exception can not be determined. '
