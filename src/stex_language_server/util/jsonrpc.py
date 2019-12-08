""" This module implements jsonrpc 2.0 and other related utilities.
Specification from: https://www.jsonrpc.org/specification#overview
"""
from __future__ import annotations
from typing import Optional, Union, List, Dict, Callable
from concurrent.futures import thread
import json
import http
import socket
import functools
from enum import IntEnum

__all__ = [
    'RequestMessage',
    'NotificationMessage',
    'ResponseMessage',
    'ErrorObject',
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
    def __init__(self, id: Union[str, int], method: str, params: Union[Dict[str, Any], List[Any]]):
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
        self.method = method
        self.params = params
        self.id = id


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
    def __init__(self, id: Union[str, int], result: Optional[Any] = None, error: Optional[ErrorObject] = None):
        ''' Initializes a response message.
        Parameters:
            id: The id of the request to respond to.
            result: Result of the method execution.
                Result object should be json serializable or use a custom json encoder.
                This must be "None" if the method failed.
            error: Information about method failure. This must be "None" if the method succeeded.
        '''
        super().__init__()
        if ((result is not None and error is not None)
            or (result is None and error is None)):
            raise ValueError('Either result or error must be defined.')
        if result is not None:
            self.result = result
        if error is not None:
            self.error = error
        self.id = id


class ErrorObject:
    " Gives more information in case a request method can't be executed by the server. "
    def __init__(self, code: int, message: str, data: Optional[Any] = None):
        ''' Constructs error object.
        Parameters:
            code: A number that indicates the error type occured.
                Error codes in range -32768 to -32000 are reserved by jsonrpc.
            message: A short description of the error.
            data: A primitive or structured value that contains additional information.
        '''
        self.code = code
        self.message = message
        if data is not None:
            self.data = data

class ErrorCodes(IntEnum):
    ''' jsonrpc reserved error codes
    Parse error: Invalid JSON was received by the server. An error occurred on the server while parsing the JSON text.
    Invalid Request: The JSON sent is not a valid Request object.
    Method not found: The method does not exist / is not available.
    Invalid params: Invalid method parameter(s).
    Internal error: Internal JSON-RPC error.
    Server error: -32000 to -32099 -> Implementation defined
    '''
    ParseError = -32700
    InvalidRequest = -32600
    MethodNotFoudn = -32601
    InvalidParams = -32602
    InternalError = -32603
    # ServerError = -32000 to -32099 (implementation defined)
    FailedToSerializeJson = -32000


class ByteBuffer:
    def __init__(self, maxsize: int = 1):
        self.buffer = b''
    
    def append(self, data: Union[str, bytes]):
        if isinstance(data, str):
            data = bytes(data, 'utf-8')
        self.buffer += data
    
    def readln(self):
        ln = None
        if b'\n' in self.buffer:
            ln, self.buffer = self.buffer.split(b'\n', maxsplit=1)
        return str(ln)
    
    def size(self) -> int:
        return len(self.buffer)
    
    def readbytes(self, count: Optional[int]) -> bytes:
        if count is None:
            data = self.buffer
        else:
            data = self.buffer[:count]
        self.buffer = self.buffer[count:]
        return data


class JsonRpcClient:
    def __init__(self, port: int, host: str = 'localhost'):
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((host, port))
        finally:
            self.socket.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, *args, **kwargs):
        self.socket.close()
    
    def call(self, method: str, id: Union[str, int], params: Union[Dict[str, Any], List[Any]]):
        pass


class JsonRpcServer:
    def __init__(
        self,
        methods: Dict[str, Callable],
        host: str = 'localhost',
        port: int = 0):
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.bind((host, port))
            self.host, self.port = self.socket.getsockname()
            self.methods = methods
        finally:
            self.socket.close()
    
    def handle_client(self, conn: socket.socket, adr):
        print('thread.start', adr)
        buffer = ByteBuffer()
        content_length = None
        while True:
            while content_length is None:
                buffer.append(conn.recv(1024))
                ln = buffer.readln()
                if ln is not None:
                    parts = ln.split(' ')
                    if (not len(parts) == 2
                        or parts[0].lower() != 'content-length:'
                        or not parts[-1].isdigit()):
                        print("invalid header", ln)
                    else:
                        content_length = int(parts[-1])
                        print('content-length:', content_length)
            while buffer.size() < content_length:
                buffer.append(conn.recv(1024))
            content = str(buffer.readbytes(content_length))
            print('content:', content_length, content)
            content_length = None
        conn.close()
        print('thread.end')

    def server_forever(self, max_workers: int = None, backlog: int = None):
        if backlog is not None:
            self.socket.listen(backlog)
        with thread.ThreadPoolExecutor(max_workers, 'jsonrpc-server') as executor:
            while True:
                conn, adr = self.socket.accept()
                conn.recv(1024)
                print('accepted', adr)
                executor.submit(self.handle_client, conn, adr)
    
    def __enter__(self):
        return self
    
    def __exit__(self, *args, **kwargs):
        self.close()
    
    def close(self):
        self.socket.close()