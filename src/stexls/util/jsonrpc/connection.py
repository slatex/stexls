from __future__ import annotations
from typing import Callable, Union, List, Optional
import asyncio
import logging
import json

from .core import MessageObject, NotificationObject, RequestObject, ResponseObject, ErrorCodes, ErrorObject
from .streams import JsonReader, JsonWriter
from .parser import MessageParser

log = logging.getLogger(__name__)

__all__ = ['JsonRpcConnection']


class JsonRpcConnection:
    ' This is a implementation for the json-rpc-protocol. '
    def __init__(
        self,
        reader: JsonReader,
        writer: JsonWriter):
        """Initializes the protocol with a reader and writer task.

        Args:
            reader (JsonReader): Input stream.
            writer (JsonWriter): Output stream.
        """
        self.reader = reader
        self.writer = writer
        self._writer_queue = asyncio.Queue()
        self._methods = {}
        self._requests = {}

    async def run_until_finished(self):
        ' Runs the protocol until all subtasks finish. '
        log.info('Connection starting.')
        try:
            await asyncio.gather(
                self._reader_task(),
                self._writer_task())
        except asyncio.CancelledError:
            log.info('Stopping Connection due to cancellation.')
        log.info('JsonRpcConnection all tasks finished. Exiting.')

    def on(self, method: str, callback: Callable):
        """Registers a method.

        Args:
            method (str): Method name to register.
            callback (Callable): The function body, that will be called.
        """
        if method in self._methods:
            raise ValueError(f'Method "{method}" is already registered with this protocol.')
        log.info('Registering json-rpc callback "%s"', method)
        self._methods[method] = callback

    async def send(
        self, message_or_batch: Union[MessageObject, List[MessageObject]]
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
                    if msg.id in self._requests:
                        raise ValueError(f'Duplicate request id: {msg.id}')
            requests = {
                msg.id: asyncio.Future()
                for msg in message_or_batch
                if isinstance(msg, RequestObject)
            }
            self._requests.update(requests)
            self._writer_queue.put_nowait(message_or_batch)
            return await asyncio.gather(*requests.values())
        elif isinstance(message_or_batch, RequestObject):
            log.debug('Dispatching request: %s', message_or_batch)
            if message_or_batch.id in self._requests:
                raise ValueError(f'Duplicate request id: {message_or_batch.id}')
            request = asyncio.Future()
            self._requests[message_or_batch.id] = request
            self._writer_queue.put_nowait(message_or_batch)
            return await request
        elif isinstance(message_or_batch, MessageObject):
            log.debug('Dispatching %s: %s.', type(message_or_batch), message_or_batch)
            self._writer_queue.put_nowait(message_or_batch)

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
        if id is not None:
            log.debug('Returning response to method call of %s(%s) with id %s.', method, params, id)
        return response

    async def _handle_message(self, message: MessageObject) -> Optional[ResponseObject]:
        """ Handles any type of jrpc message object.

        Args:
            message (MessageObject): Incoming message object.

        Returns:
            Optional[ResponseObject]: Response to request messages.
        """
        if isinstance(message, RequestObject):
            log.info('Calling request "%i" method "%s".', message.id, message.method)
            return await self._call(message.method, getattr(message, 'params', None), message.id)
        elif isinstance(message, NotificationObject):
            log.info('Calling notification method "%s".', message.method)
            await self._call(message.method, getattr(message, 'params', None))
        elif isinstance(message, ResponseObject):
            request: asyncio.Future = self._requests.get(getattr(message, 'id', None))
            if request is None:
                log.warning('Response with unexpected id (%s): %s', getattr(message, 'id', None), message)
            else:
                del self._requests[message.id]
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
                try:
                    obj = await self.reader.read_json()
                    if obj is None:
                        log.debug('Reader task read EOF.')
                        break
                    parser = MessageParser(obj)
                    handled_messages = await asyncio.gather(*map(self._handle_message, parser.valid))
                    responses = list(filter(None, handled_messages)) + parser.errors
                except json.JSONDecodeError as e:
                    log.exception('Reader encountered exception while parsing json.')
                    responses = ResponseObject(None, error=ErrorObject(ErrorCodes.ParseError, message=str(e)))
                if not responses:
                    log.debug('Reader generated empty response.')
                else:
                    log.debug('Reader sending responses to the writer task: %s', responses)
                    if parser.is_batch:
                        await self._writer_queue.put(responses)
                    else:
                        for response in responses:
                            await self._writer_queue.put(response)
        except (EOFError, asyncio.CancelledError, asyncio.IncompleteReadError) as e:
            log.debug('Reader task exiting because of %s.', type(e))
        await self._writer_queue.put(self)
        log.info('Reader task finished.')

    async def _writer_task(self):
        ' Launches and waits for completion of the writer stream task, which writes outgoing messages. '
        log.info('Writer task started.')
        try:
            while True:
                log.debug('Writer waiting for message from queue.')
                message: Union[MessageObject, List[MessageObject]] = await self._writer_queue.get()
                if message == self:
                    log.info('Writer task received stop message. Exiting.')
                    break
                if not message:
                    log.debug('Writer throwing invalid message away: %s', message)
                else:
                    log.debug('Writing message: %s', message)
                    self.writer.write_json(message)
        except asyncio.CancelledError:
            log.debug('Writer task stopped because of cancellation event.')
        log.info('Writer task finished.')
