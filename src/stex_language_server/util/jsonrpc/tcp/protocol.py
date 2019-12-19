from typing import Optional, Awaitable
import asyncio
import logging
from collections import defaultdict
from .. import protocol
from .. import core
from .. import dispatcher

log = logging.getLogger(__name__)

__all__ = ['JsonRpcTcpProtocol']


class TcpReaderStream(protocol.ReaderStream):
    def __init__(self, reader: asyncio.StreamReader, encoding: str = 'utf-8', linebreak: str = '\r\n'):
        self._reader = reader
        self._encoding = encoding
        self._linebreak = linebreak

    async def read(self) -> Optional[protocol.JsonRpcMessage]:
        content_length = None
        content_type = None
        log.debug('Start reading from stream.')
        while True:
            log.debug('Waiting for a line.')
            ln = await self._reader.readline()
            if not ln:
                log.info('Reader stream received EOF while waiting for line. Returning None.')
                return None
            ln = ln.decode(self._encoding).strip()
            if not ln:
                log.debug('Received terminator line.')
                if content_length is not None and content_length > 0:
                    log.debug('Header content-length is set to "%i". Header is valid.', content_length)
                    break
                else:
                    log.warning('Header is in inconsistent state after receiving terminator. Resetting.')
                    content_length = None
                    content_type = None
                    continue
            log.debug('Line received: %s', ln)
            parts = ln.split(':')
            parts = tuple(map(str.lower, map(str.strip, parts)))
            if (len(parts) != 2
                or parts[0] not in ('content-length', 'content-type')
                or (parts[0] == 'content-length' and not parts[1].isdigit())):
                log.debug('Received line is invalid. Resetting.')
                content_length = None
                content_type = None
                continue
            setting, value = parts
            if setting == 'content-length':
                content_length = int(value)
                log.debug('Setting content-length to "%i".', content_length)
            else:
                content_type = value
                log.debug('Setting content-type to "%s"', content_type)
        log.debug('Reading "%i" bytes.', content_length)
        try:
            content = await self._reader.read(content_length)
            if not content or len(content) != content_length:
                raise EOFError()
        except (EOFError, asyncio.IncompleteReadError):
            log.warning('Reader stream received eof while waiting for %i bytes.', content_length)
            return None
        content = content.decode(self._encoding)
        log.debug('Content received: "%s"', content)
        return protocol.JsonRpcMessage.from_json(content)


class TcpWriterStream(protocol.WriterStream):
    def __init__(self, writer: asyncio.StreamWriter, encoding: str = 'utf-8', linebreak: str = '\r\n'):
        self._writer = writer
        self._encoding = encoding
        self._linebreak = linebreak

    async def write(self, message: protocol.JsonRpcMessage):
        for string in message.to_json():
            content = bytes(string, self._encoding)
            header_string = (f'Content-Length: {len(content)}{self._linebreak}'
                             f'Content-Type: charset={self._encoding}{self._linebreak}{self._linebreak}')
            header = bytes(header_string, self._encoding)
            self._writer.write(header + content)


class JsonRpcTcpProtocol(
    protocol.JsonRpcProtocol,
    protocol.InputHandler,
    protocol.MessageHandler,
    dispatcher.DispatcherTarget):
    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter):
        self.__reader = TcpReaderStream(reader)
        self.__writer = TcpWriterStream(writer)
        super().__init__(self, self, self.__reader, self.__writer)
        self.__user_input_queue = asyncio.Queue()
        self.__futures = defaultdict(asyncio.Future)
        self.__dispatcher = None
    
    async def close(self):
        await super().close()
        log.info('JsonRpcTcpProtocol close() called.')
        await self.__user_input_queue.put(None)
        for id, fut in self.__futures.items():
            log.debug('Cancelling future id %i', id)
            fut.cancel()
    
    def set_dispatcher(self, dispatcher: dispatcher.Dispatcher):
        self.__dispatcher = dispatcher
    
    async def handle_request(self, request: core.RequestObject):
        params = getattr(request, 'params', None)
        log.debug('Handling request with id %i: %s(%s)', request.id, request.method, params)
        return await self.__dispatcher.call(request.method, params, request.id)

    async def handle_notification(self, notification: core.NotificationObject):
        params = getattr(notification, 'params', None)
        log.debug('Handling notification: %s(%s)', notification.method, params)
        await self.__dispatcher.call(notification.method, params)

    async def handle_response(self, response: core.ResponseObject):
        if response.id is None:
            log.warning('Received response without id: %s', response)
        elif response.id not in self.__futures:
            log.warning('Received response with invalid id (%i): %s', response.id, response)
        else:
            if hasattr(response, 'error'):
                log.warning('Resolving request id %i with exception: %s', response.id, response)
                self.__futures[response.id].set_exception(Exception(response.error))
            elif hasattr(response, 'result'):
                log.debug('Resolving request id %i with result: %s', response.id, response)
                self.__futures[response.id].set_result(response.result)
            else:
                log.warning('Received response (id %i) without result or error: %s', response.id, response)
    
    async def get_user_input(self):
        log.debug('Getting user input: %s', self.__user_input_queue)
        return await self.__user_input_queue.get()
    
    async def dispatch(self, message: core.MessageObject) -> Optional[Awaitable[core.ResponseObject]]:
        log.debug('Dispatching message: %s', message)
        await self.__user_input_queue.put(protocol.JsonRpcMessage(objects=(message,)))
        log.debug('Message dispatched: %s', self.__user_input_queue)
        if isinstance(message, core.RequestObject):
            log.debug('Waiting for result of dispatched request.')
            response = await self.__futures[message.id]
            del self.__futures[message.id]
            return response
