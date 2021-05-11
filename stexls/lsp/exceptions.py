from ..jsonrpc import exceptions
from ..vscode import ErrorCodes


class ServerNotInitializedException(exceptions.JsonRpcException):
    def __init__(self, message: str = 'Server not initialized', data=None) -> None:
        super().__init__(ErrorCodes.ServerNotInitialized.value, message=message, data=data)
