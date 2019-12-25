from __future__ import annotations
from typing import Iterable, Callable, Iterator, Tuple, Union
import asyncio
import logging
from .core import *
from .dispatcher import DispatcherTarget
from .hooks import extract_methods
from .streams import JsonStreamReader, JsonStreamWriter, AsyncReaderStream, AsyncWriterStream
from .util import validate_json, restore_message
from .method_provider import MethodProvider

log = logging.getLogger(__name__)

__all__ = ('JsonRpcProtocol',)


class JsonRpcProtocol(DispatcherTarget):
    ' This is a implementation for the json-rpc-protocol. '
    def __init__(
        self, reader: AsyncReaderStream, writer: AsyncWriterStream, linebreak: str = '\r\n', encoding: str = 'utf-8'):
        self.__reader = JsonStreamReader(reader, linebreak=linebreak, encoding=encoding)
        self.__writer = JsonStreamWriter(writer, linebreak=linebreak, encoding=encoding)
        self.__writer_queue = asyncio.Queue()
        self.__methods = extract_methods(self)
        self.__requests = {}
        self.__method_provider: MethodProvider = None
        self.__task_loop: asyncio.Future = None
    
    def set_method_provider(self, provider: MethodProvider):
        ' Sets the protocols method provider used to resolve requests and notifications. '
        self.__method_provider = provider

    async def run_until_finished(self):
        ' Runs the protocol until all subtasks finish. '
        log.info('JsonRpcProtocol starting.')
        self.__task_loop = asyncio.gather(
            self._reader_task(),
            self._writer_task())
        try:
            await self.__task_loop
        except asyncio.CancelledError:
            log.info('Stopping JsonRpcProtocol due to cancellation.')
        log.info('JsonRpcProtocol all tasks finished. Exiting.')

    async def dispatch(
        self, message_or_batch: Union[MessageObject, List[MessageObject]]
        ) -> Optional[ResponseObject, List[ResponseObject]]:
        if isinstance(message_or_batch, list):
            log.debug('Dispatching batch: %s', message_or_batch)
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
            request = asyncio.Future()
            self.__requests[message_or_batch.id] = request
            self.__writer_queue.put_nowait(message_or_batch)
            return await request
        elif isinstance(message_or_batch, MessageObject):
            log.debug('Dispatching %s: %s.', type(message_or_batch), message_or_batch)
            self.__writer_queue.put_nowait(message_or_batch)
    
    async def call(
        self,
        method: str,
        params: Union[list, dict, None],
        id: Union[int, str] = None) -> Optional[ResponseObject]:
        ' Calls the given method with the parameters and generates a response object according to the results. '
        log.info('Calling method %s(%s) with id %s.', method, params, id)
        if not self.__method_provider.is_method(method):
            log.warning('Method %s not found.', method)
            response = ResponseObject(
                id, error=ErrorObject(ErrorCodes.MethodNotFound, data=method))
        else:
            try:
                result = await self.__method_provider.call(method, params)
                log.debug('Method %s(%s) call successful.', method, params)
                response = ResponseObject(
                    id, result=result)
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
        self, message_or_batch: Any) -> Optional[ResponseObject, List[ResponseObject]]:
        if isinstance(message_or_batch, list):
            log.debug('Handling raw json batch: %s', message_or_batch)
            tasks = [
                asyncio.create_task(self._handle_message(msg))
                for msg in message_or_batch
            ]
            return list(filter(None, await asyncio.gather(*tasks)))
        else:
            return await self._handle_message(message_or_batch)
    
    async def _handle_message(self, message: Any) -> Optional[ResponseObject]:
        log.debug('Handling message: %s', message)
        invalid = validate_json(message)
        if invalid is not None:
            log.debug('Message handled is invalid: %s', invalid)
            return invalid
        message = restore_message(message)
        log.debug('Restored original message from json: %s', message)
        if isinstance(message, RequestObject):
            log.debug('Calling request (%i) method %s.', message.id, message.method)
            return await self.call(message.method, getattr(message, 'params', None), message.id)
        elif isinstance(message, NotificationObject):
            log.debug('Calling notification method %s.', message.method)
            await self.call(message.method, getattr(message, 'params', None))
        elif isinstance(message, ResponseObject):
            request: asyncio.Future = self.__requests.get(getattr(message, 'id', None))
            if request is None:
                log.warning('Response with unexpected id (%s): %s', getattr(message, 'id', None), message)
            else:
                del self.__requests[message.id]
                if hasattr(message, 'error'):
                    log.warning('Resolving request %i with error: %s', message.id, message.error)
                    request.set_exception(message.error.to_exception())
                else:
                    log.debug('Resolving request %i with result: %s', message.id, message.result)
                    request.set_result(message.result)
                
    async def _reader_task(self):
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
                log.debug('Sending responses to the writer task: %s', responses)
                await self.__writer_queue.put(responses)
        except (EOFError, asyncio.CancelledError, asyncio.IncompleteReadError) as e:
            log.info('Reader task exiting because of %s.', type(e))
            self.__writer_queue.put_nowait(self)
        log.info('Reader task finished.')
    
    async def _writer_task(self):
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
