from __future__ import annotations
from typing import Callable, Union, List, Optional, Any, Dict, Awaitable, Tuple
import re
import asyncio
import logging
import json
import os
import sys

from .core import MessageObject, NotificationObject, RequestObject, ResponseObject, ErrorCodes, ErrorObject
from .streams import JsonStream
from .parser import MessageParser

log = logging.getLogger(__name__)

__all__ = ['JsonRpcConnection', 'start_server', 'open_connection', 'open_stdio_connection']


class JsonRpcConnection:
    ' This is a implementation for the json-rpc-protocol. '
    def __init__(self, stream: JsonStream):
        """ Initializes the connection with a stream which can read and write json data.

        Args:
            stream: IO Stream which handles json serialization and protocol header stuff.
        """
        self._stream = stream
        self._methods = {}
        self._requests = {}

    def on(self, method: str, callback: Callable):
        """ Registers a method as a request and notification handler.

        Args:
            method (str): Method name to register.
            callback (Callable): The function body that will be called.
        """
        if method in self._methods:
            raise ValueError(f'Method "{method}" is already registered with this protocol.')
        self._methods[method] = callback

    def send(self, message: Union[NotificationObject, RequestObject]) -> Optional[Awaitable[Any]]:
        """ Sends a message of any type.

        Args:
            message: A message you want to send.

        Returns:
            Optional[Awaitable[Any]]: A future with the result of a request.
        """
        if isinstance(message, NotificationObject):
            self.send_notification(message)
        elif isinstance(message, ResponseObject):
            raise ValueError('The user should not send response objects.')
        elif isinstance(message, RequestObject):
            return self.send_request(message)

    def send_notification(self, message: NotificationObject):
        ' Specifically sends a notification. '
        self._stream.write_json(message)

    def send_request(self, message: RequestObject) -> Awaitable[Any]:
        ' Sends a request and returns the future object with the results. '
        if message.id in self._requests:
            raise ValueError('Duplicate message id.')
        result = asyncio.Future()
        self._requests[message.id] = result
        self._stream.write_json(message)
        return result

    def _handle_response(self, response: ResponseObject):
        ''' Handles an response object.

        Performs error checks and resolves request if ids match.
        '''
        if response.id is None:
            log.warning('Received response without id:\n%s', response)
        elif response.id not in self._requests:
            log.warning('Received response with unknown id:\n%s', response)
        else:
            log.debug('Resolving request:\n%s', response)
            result = self._requests[response.id]
            del self._requests[response.id]
            if hasattr(response, 'error'):
                result.set_exception(response.error.to_exception())
            else:
                result.set_result(response.result)

    async def _handle_notification(self, notification: NotificationObject):
        ' Handles incoming notifications. This only calls the contained method. '
        await self.call(
            notification.method, getattr(notification, 'params', None))

    async def _handle_request(self, request: RequestObject) -> Awaitable[Any]:
        """ Handles a request.

        Calls the contained method with parameters and returns the response object.

        Returns:
            ResponseObject: ResponseObject with results or errors.
        """
        return await self.call(
            request.method, getattr(request, 'params', None), request.id)

    async def _handle_message(
        self, message: Union[RequestObject, NotificationObject, ResponseObject]) -> Optional[ResponseObject]:
        " Handles any type of incoming message and returns the response if it is a request. "
        if isinstance(message, ResponseObject):
            self._handle_response(message)
        elif isinstance(message, NotificationObject):
            await self._handle_notification(message)
        elif isinstance(message, RequestObject):
            return await self._handle_request(message)

    async def call(
        self,
        method: str,
        params: Union[list, dict, None] = None,
        id: Union[int, str] = None) -> Optional[ResponseObject]:
        """ Calls a registered method.

        Searches for the specified method and executes it using the list or dict
        of parameters. If an ID is given, an response will be returned with the
        execution results.

        Args:
            method: Method to execute.
            params: Optional parameters passed to the method.
            id: Optional response id. Responses will only be generated if this is not None.

        Returns:
            Optional[ResponseObject]: Response object with the given ID if given.
        """
        if not method in self._methods:
            log.warning('Method "%s" not found.', method, exc_info=1)
            response = ResponseObject(
                id, error=ErrorObject(ErrorCodes.MethodNotFound, data=method))
        else:
            try:
                if params is None:
                    result = self._methods[method]()
                elif isinstance(params, list):
                    result = self._methods[method](*params)
                elif isinstance(params, dict):
                    result = self._methods[method](**params)
                else:
                    raise ValueError(f'Method params of invalid type: {type(params)}')
                log.debug('Method %s(%s) call successful.', method, params)
                if asyncio.iscoroutine(result):
                    log.debug(f'Called method "{method}" returned coroutine.')
                    result = await result
                response = ResponseObject(id, result=result)
            except TypeError as e:
                log.warning('Method %s(%s) threw possible InvalidParams error.', method, params, exc_info=1)
                response = ResponseObject(
                    id, error=ErrorObject(ErrorCodes.InvalidParams, data=str(e)))
            except Exception as e:
                log.exception('Method %s(%s) raised an unexpected error.', method, params)
                response = ResponseObject(
                    id, error=ErrorObject(ErrorCodes.InternalError, data=str(e)))
        return response

    async def _handle(self, obj: dict):
        """ Handles an incoming raw message.

        The input is parsed as a MessageObject or batch of message objects.
        the parsed messages are handled in parallel
        and responses and errors are written to the output stream.

        Args:
            obj: Some dictionary parsed using json.
        """
        parser = MessageParser(obj)
        log.debug(
            "Parsed message (%i valid, %i errors).", len(parser.valid), len(parser.errors))
        responses = await asyncio.gather(
            *map(self._handle_message, parser.valid))
        responses = filter(None, responses)
        responses = list(responses) + parser.errors
        if not responses:
            log.debug('No responses to send back.')
        elif parser.is_batch:
            self._stream.write_json(responses)
        else:
            for response in responses:
                self._stream.write_json(response)

    async def run_forever(self):
        ' Launches the incoming message reader. '
        log.info('Reader task started.')
        try:
            while True:
                log.debug('Waiting for message from stream.')
                try:
                    obj = await self._stream.read_json()
                    log.debug('Message received: %s', obj)
                    asyncio.create_task(self._handle(obj))
                except json.JSONDecodeError as e:
                    log.exception('Reader encountered exception while parsing json.')
                    response = ResponseObject(None, error=ErrorObject(ErrorCodes.ParseError, message=str(e)))
                    self._stream.write_json(response)
        except (EOFError, asyncio.CancelledError, asyncio.IncompleteReadError) as e:
            log.debug('Reader task exiting because of %s.', type(e))
        log.info('Reader task finished.')

async def start_server(
    dispatcher_factory: type,
    host: str = 'localhost',
    port: int = 0,
    encoding: str = 'utf-8',
    charset: str = None,
    newline: str = '\n') -> Tuple[Tuple[str, int], asyncio.Task]:
    """ Starts a tcp server.

    Args:
        dispatcher_factory: A Dispatcher type.
        host: Host name to connect to.
        port: Port to connect to.
        encoding: Encoding of the sent binary data.
        charset: Optional encoding of the sent contents. Uses encoding if None.
        newline: Which character terminates lines.

    Returns:
        Tuple[Tuple[str, int], asyncio.Task]: Returns a tuple of host name and port the
            server is running on, as well as the asyncio task the server runs on.
    """
    def connect_fun(r, w):
        peername = w.get_extra_info('peername')
        log.info('Incoming connection from %s', peername)
        stream = JsonStream(
            r, w, encoding=encoding, charset=charset, newline=newline)
        conn = JsonRpcConnection(stream)
        _ = dispatcher_factory(conn)
        asyncio.create_task(conn.run_forever())
    server = await asyncio.start_server(connect_fun, host=host, port=port)
    async def task():
        async with server:
            await server.serve_forever()
    server_name = server.sockets[0].getsockname()[:2]
    server_task = asyncio.create_task(task())
    return server_name, server_task

async def open_connection(
    dispatcher_factory: type,
    host: str = 'localhost',
    port: int = 0,
    encoding: str = 'utf-8',
    charset: str = None,
    newline: str = '\n') -> JsonStream:
    """ Opens a connection to a tcp server.

    Args:
        dispatcher_factory: A Dispatcher type.
        host: Host name to connect to.
        port: Port to connect to.
        encoding: Encoding of the sent binary data.
        charset: Optional encoding of the sent contents.
        newline: Which character terminates lines.

    Returns:
        (Dispatcher, Task): Returns the dispatcher instance for this connection
            as well as the task which runs the client's event loop.
    """
    reader, writer = await asyncio.open_connection(host=host, port=port)
    stream = JsonStream(
        reader, writer, encoding=encoding, charset=charset, newline=newline)
    conn = JsonRpcConnection(stream)
    conn_task = asyncio.create_task(conn.run_forever())
    dispatcher = dispatcher_factory(conn)
    return dispatcher, conn_task

async def open_stdio_connection(
    dispatcher_factory: type,
    input_fd: int = 'stdin',
    output_fd: int = 'stdout',
    encoding: str = 'utf-8',
    charset: str = None,
    newline: str = '\n',
    loop = None) -> JsonStream:
    """ Opens connection using stdio.

    Takes input and output file descriptors and uses
    them as the streams for the json connection.

    Args:
        dispatcher_factory: A Dispatcher type.
        input_fd: Input file descriptor of pipe.
            Can also be a string of "stdin".
        output_fd: Output file descriptor of pipe.
            Can also be a string of "stdout" or "stderr".
        encoding: Encoding of the sent binary data.
        charset: Optional encoding of the sent contents.
        newline: Which character terminates lines.
        loop: Asyncio event loop.
    """
    translate = {
        'stdin': sys.stdin.fileno,
        'stdout': sys.stdout.fileno,
        'stderr': sys.stderr.fileno,
    }
    input_fd = translate.get(input_fd, lambda: input_fd)()
    output_fd = translate.get(output_fd, lambda: output_fd)()
    input_pipe = os.fdopen(input_fd, 'rb', 0)
    output_pipe = os.fdopen(output_fd, 'wb', 0)
    loop = loop or asyncio.get_event_loop()
    reader = asyncio.StreamReader(loop=loop)
    await loop.connect_read_pipe(
        lambda: asyncio.StreamReaderProtocol(reader, loop=loop), input_pipe)
    writer_transport, writer_protocol = await loop.connect_write_pipe(
        lambda: asyncio.streams.FlowControlMixin(loop=loop),
        output_pipe)
    writer = asyncio.streams.StreamWriter(
        writer_transport, writer_protocol, None, loop)
    stream = JsonStream(
        reader, writer, encoding=encoding, charset=charset, newline=newline)
    conn = JsonRpcConnection(stream)
    conn_task = asyncio.create_task(conn.run_forever())
    dispatcher = dispatcher_factory(conn)
    return dispatcher, conn_task
