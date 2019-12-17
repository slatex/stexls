from typing import Optional, Awaitable
import asyncio
import logging
from .message import Header, Message, HeaderItem

log = logging.getLogger(__name__)

class MessageReaderStream:
    def __init__(
        self,
        reader: asyncio.StreamReader,
        header: Header = None,
        header_encoding: str = 'utf-8',
        linebreak: str = '\r\n'):
        self._header = header or Header()
        self._reader = reader
        self._header_encoding = header_encoding
        self._linebreak = linebreak

    async def read(self) -> Awaitable[str]:
        self._header.reset()
        while True:
            try:
                log.debug('Waiting for a line.')
                line = await self._reader.readline()
                if not line:
                    log.debug('EOF while waiting for a line.')
                    raise EOFError()
                try:
                    line = line.decode(self._header_encoding)
                except UnicodeDecodeError:
                    log.error('Failed to decode stream using encoding %s', self._header_encoding)
                    self._header.reset()
                    continue
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
                        message = Message(self._header.copy(), content)
                        decoded_message_content = message.decode_content()
                        return decoded_message_content
                    else:
                        log.warning('Header in invalid state after terminator: Resetting.')
                        self._header.reset()
                        continue
                else:
                    try:
                        log.info('Line received: "%s"', line.strip())
                        self._header.add_line(line)
                    except:
                        log.warning('Resetting after invalid line: "%s"', line.strip())
                        self._header.reset()
                        continue
            except asyncio.CancelledError:
                log.debug('Reader stream exit: Cancelled')
                raise
            except EOFError:
                log.debug('Reader stream exit: EOF')
                raise
            except:
                log.exception('Unexpected error in reader stream.')
                self._header.reset()

class MessageWriterStream:
    def __init__(
        self,
        writer: asyncio.StreamWriter,
        encoding: str = 'utf-8',
        linebreak: str = '\r\n'):
        self._writer = writer
        self._encoding = encoding
        self._linebreak = linebreak
        self._header = Header([
            HeaderItem('Content-Length', int, required=True),
            HeaderItem('Content-Type', str),
        ])
        self._header.set_value('Content-Type', f'charset={encoding}')

    def write(self, content: str):
        log.debug('Writing message:\n\n%s', content)
        try:
            data = bytes(content, self._encoding)
            self._header.set_value('Content-Length', len(data))
            message = Message(self._header, data)
            serialized = message.serialize(self._encoding, self._linebreak)
            self._writer.write(serialized)
        except:
            log.exception('Failed to write message:\n\n%s', content)
