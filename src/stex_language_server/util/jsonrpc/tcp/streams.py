from typing import Optional, Awaitable
import asyncio
import logging
from .message import Header, Message

log = logging.getLogger(__name__)

class MessageReaderStream:
    def __init__(
        self,
        reader: asyncio.StreamReader,
        header: Header = None,
        header_encoding: str = 'utf-8',
        linebreak: bytes = b'\r\n'):
        self._header = header or Header()
        self._reader = reader
        self._header_encoding = header_encoding
        self._linebreak = linebreak

    async def read(self) -> Awaitable[Message]:
        self._header.reset()
        while True:
            log.debug('Waiting for a line.')
            line = await self._reader.readline()
            if not line:
                log.debug('EOF while waiting for a line.')
                raise EOFError()
            if line == self._linebreak:
                log.debug('Header terminator received.')
                if self._header.ready():
                    content_length = self._header.get_value('content-length')
                    log.debug('Waiting for %i bytes.', content_length)
                    try:
                        content = await self._reader.readexactly(content_length)
                    except asyncio.IncompleteReadError:
                        log.warning('IncompleteReadError read while waiting. Connection lost?')
                        raise EOFError()
                    return Message(self._header.copy(), content)
                else:
                    log.warn('Header in invalid state after terminator: Resetting.')
                    self._header.reset()
                    continue
            else:
                try:
                    line = line.decode(self._header_encoding)
                except UnicodeDecodeError:
                    log.error('Failed to decode stream using encoding %s', self._header_encoding)
                    self._header.reset()
                    continue
                try:
                    log.info('Line received: "%s"', line.strip())
                    self._header.add_line(line)
                except:
                    log.warning('Resetting after invalid line: "%s"', line.strip())
                    self._header.reset()
                    continue


class MessageWriterStream:
    def __init__(
        self,
        writer: asyncio.StreamWriter,
        header_encoding: str = 'utf-8',
        linebreak: bytes = b'\r\n'):
        self._writer = writer
        self._header_encoding = header_encoding
        self._linebreak = linebreak
    
    async def write(self, message: Message):
        data = message.serialize(self._header_encoding, self._linebreak)
        return await self._writer.write(data)
