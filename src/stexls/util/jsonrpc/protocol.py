from __future__ import annotations
from typing import Iterable, Callable, Iterator, Tuple, Union
import asyncio
import logging
from .core import *
from .streams import JsonStreamReader, JsonStreamWriter, AsyncReaderStream, AsyncWriterStream
from .util import validate_json, restore_message

log = logging.getLogger(__name__)

__all__ = ('JsonRpcProtocol',)


class JsonRpcProtocol:
    ' This is a implementation for the json-rpc-protocol. '
    def __init__(
        self,
        reader: AsyncReaderStream,
        writer: AsyncWriterStream,
        linebreak: str = '\r\n',
        encoding: str = 'utf-8'):
        """Initializes the protocol with a reader and writer task.

        Args:
            reader (AsyncReaderStream): Input stream.
            writer (AsyncWriterStream): Output stream.
            linebreak (str, optional): Message linebreak character. Defaults to '\r\n'.
            encoding (str, optional): Encoding of the streams. Defaults to 'utf-8'.
        """
        self.__reader = JsonStreamReader(reader, linebreak=linebreak, encoding=encoding)
        self.__writer = JsonStreamWriter(writer, linebreak=linebreak, encoding=encoding)
        self.__writer_queue = asyncio.Queue()
        self.__methods = {}
        self.__requests = {}

    async def run_until_finished(self):
        ' Runs the protocol until all subtasks finish. '
        log.info('JsonRpcProtocol starting.')
        try:
            await asyncio.gather(
                self._reader_task(),
                self._writer_task())
        except asyncio.CancelledError:
            log.info('Stopping JsonRpcProtocol due to cancellation.')
        log.info('JsonRpcProtocol all tasks finished. Exiting.')

    def on(self, method: str, callback: Callable):
        """Registers a method.

        Args:
            method (str): Method name to register.
            callback (Callable): The function body, that will be called.
        """
        if method in self.__methods:
            raise ValueError(f'Method "{method}" is already registered with this protocol.')
        log.info('Registering json-rpc callback "%s"', method)
        self.__methods[method] = callback

    async def send(
        self,
        message_or_batch: Union[MessageObject, List[MessageObject]]
        ) -> Optional[ResponseObject, List[ResponseObject]]:
        """Sends a message or batch of messages over the connection.

        Args:
            message_or_batch (Union[MessageObject, List[MessageObject]]):
                Single message object or batch of message objects.

        Raises:
            ValueError: If a request has an id that already exists.

        Returns:
            Optional[ResponseObject, List[ResponseObject]]:
                A response object or list ob response object for each
                request that was sent.
        """
        if isinstance(message_or_batch, list):
            log.debug('Dispatching batch: %s', message_or_batch)
            for msg in message_or_batch:
                if isinstance(msg, RequestObject):
                    if msg.id in self.__requests:
                        raise ValueError(f'Duplicate request id: {msg.id}')
            requests = {
                msg.id: asyncio.Future()
                for msg in message_or_batch
                if isinstance(msg, RequestObject)
            }
            self.__requests.update(requests)
            self.__writer_queue.put_nowait(message_or_batch)
            return await asyncio.gather(*requests.values())
        elif isinstance(message_or_batch, RequestObject):
            log.debug('Dispatching request: %s', message_or_batch)
            if message_or_batch.id in self.__requests:
                raise ValueError(f'Duplicate request id: {message_or_batch.id}')
            request = asyncio.Future()
            self.__requests[message_or_batch.id] = request
            self.__writer_queue.put_nowait(message_or_batch)
            return await request
        elif isinstance(message_or_batch, MessageObject):
            log.debug('Dispatching %s: %s.', type(message_or_batch), message_or_batch)
            self.__writer_queue.put_nowait(message_or_batch)

    async def _call(
        self,
        method: str,
        params: Union[list, dict, None] = None,
        id: Union[int, str] = None) -> Optional[ResponseObject]:
        """Calls a registered method callback with the given parameters.

        Args:
            method (str): The callback method to call.
            params (Union[list, dict, None]): Optional list or dict of parameters. Defaults to None.
            id (Union[int, str], optional): Optional id if a response should be awaited. Defaults to None.

        Raises:
            ValueError: Raised if the type of the parameters argument is invalid.

        Returns:
            Optional[ResponseObject]: A respose object if the id was specified.
        """
        log.info('Calling method %s(%s) with id %s.', method, params, id)
        if not method in self.__methods:
            log.warning('Method "%s" not found.', method, exc_info=1)
            response = ResponseObject(
                id, error=ErrorObject(ErrorCodes.MethodNotFound, data=method))
        else:
            try:
                if params is None:
                    result = self.__methods[method]()
                elif isinstance(params, list):
                    result = self.__methods[method](*params)
                elif isinstance(params, dict):
                    result = self.__methods[method](**params)
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
        if id is not None:
            log.debug('Returning response to method call of %s(%s) with id %s.', method, params, id)
        return response

    async def _handle_message_or_batch(
        self,
        message_or_batch: Union[List[dict], dict]) -> Optional[ResponseObject, List[ResponseObject]]:
        """Multiplexes the message handler between a single message or a batch.

        The provided messages are dictionaries of deserialized json strings.

        Args:
            message_or_batch (Union[List[dict], dict]):
                Single dictionary or batch of dictionaries.

        Returns:
            Optional[ResponseObject, List[ResponseObject]]:
                Response objects which need to be sent back to sender.
                This may be responses stating, that the input object was invalid,
                or the result of a request execution.
        """
        if isinstance(message_or_batch, list):
            log.debug('Handling raw json batch: %s', message_or_batch)
            tasks = [
                self._handle_message(msg)
                for msg in message_or_batch
            ]
            return list(filter(None, await asyncio.gather(*tasks)))
        else:
            return await self._handle_message(message_or_batch)

    async def _handle_message(self, message: dict) -> Optional[ResponseObject]:
        """Handles a single incoming message.

        The incoming message must be a deserialized json dictionary.
        Other types will result in a an invalid message response.
        Responses returned by this method must be returned to the sender.

        Args:
            message (dict): Message to handle. Deserialized json object.

        Returns:
            Optional[ResponseObject]: Response with invalid json object parsing status,
                or execution result.
        """
        log.debug('Handling message: %s', message)
        invalid = validate_json(message)
        if invalid is not None:
            log.debug('Handled message is invalid, creating response: %s', invalid)
            return invalid
        message = restore_message(message)
        log.debug('Restored original message from json: %s', message)
        if isinstance(message, RequestObject):
            log.info('Calling request "%i" method "%s".', message.id, message.method)
            return await self._call(message.method, getattr(message, 'params', None), message.id)
        elif isinstance(message, NotificationObject):
            log.info('Calling notification method "%s".', message.method)
            await self._call(message.method, getattr(message, 'params', None))
        elif isinstance(message, ResponseObject):
            request: asyncio.Future = self.__requests.get(getattr(message, 'id', None))
            if request is None:
                log.warning('Response with unexpected id (%s): %s', getattr(message, 'id', None), message)
            else:
                del self.__requests[message.id]
                if hasattr(message, 'error'):
                    log.warning('Resolving request "%i" with error: %s', message.id, message.error)
                    request.set_exception(message.error.to_exception())
                else:
                    log.info('Resolving id "%i".', message.id)
                    request.set_result(message.result)

    async def _reader_task(self):
        ' Launches and waits for completion of the reader stream task which reads incoming messages. '
        log.info('Reader task started.')
        try:
            while True:
                log.debug('Waiting for message from stream.')
                header: dict = await self.__reader.header()
                if not header or 'content-length' not in header:
                    log.warning('Invalid header: %s', header)
                    continue
                log.debug('Header received: %s', header)
                message = await self.__reader.read(header)
                log.debug('Message content received: %s', message)
                responses = await self._handle_message_or_batch(message)
                if not responses:
                    log.debug('Reader generated empty response.')
                else:
                    log.debug('Reader sending responses to the writer task: %s', responses)
                    await self.__writer_queue.put(responses)
        except (EOFError, asyncio.CancelledError, asyncio.IncompleteReadError) as e:
            log.debug('Reader task exiting because of %s.', type(e))
            self.__writer_queue.put_nowait(self)
        log.info('Reader task finished.')

    async def _writer_task(self):
        ' Launches and waits for completion of the writer stream task, which writes outgoing messages. '
        log.info('Writer task started.')
        try:
            while True:
                log.debug('Writer waiting for message from queue.')
                message: Union[MessageObject, List[MessageObject]] = await self.__writer_queue.get()
                if message == self:
                    log.info('Writer task received stop message. Exiting.')
                    break
                if not message:
                    log.debug('Writer throwing invalid message away: %s', message)
                else:
                    log.debug('Writing message: %s', message)
                    await self.__writer.write(message)
        except asyncio.CancelledError:
            log.debug('Writer task stopped because of cancellation event.')
        log.info('Writer task finished.')
