from typing import Union, Optional, Any, Dict
import io
import sys
import asyncio
import functools
import re
import json
import logging

log = logging.getLogger(__name__)

__all__ = (
    'AsyncReaderStream',
    'AsyncBufferedReaderStream',
    'AsyncIoReaderStream',
    'AsyncWriterStream',
    'AsyncBufferedWriterStream',
    'AsyncIoWriterStream',
    'JsonStreamReader',
    'JsonStreamWriter'
)

class AsyncReaderStream:
    ' Interface for a stream that can read lines and bytes asynchronously. '
    async def readuntil(self, separator: bytes = b'\n') -> bytes:
        ''' Reads data until separator is reached.
            Must return en empty string if EOF is encountered.
        '''
        raise NotImplementedError()

    async def read(self, count: int) -> bytes:
        ''' Reads exactly count many bytes from stream and returns them.
            Must return an empty string if EOF is encountered.
        '''
        raise NotImplementedError()


class AsyncBufferedReaderStream(AsyncReaderStream):
    def __init__(self, stream: io.BufferedReader):
        self._stream = stream
        self._buffer = b''

    async def readuntil(self, separator: bytes = b'\n') -> bytes:
        while separator not in self._buffer:
            data = self._stream.read1()
            if not data:
                return b''
            self._buffer += data
        line, self._buffer = self._buffer.split(separator, maxsplit=1)
        return line + separator
    
    async def read(self, count: int = -1) -> bytes:
        loop = asyncio.get_event_loop()
        partial = functools.partial(self._stream.read, count)
        data = await loop.run_in_executor(None, partial)
        return data


class AsyncIoReaderStream(AsyncReaderStream):
    ' Adapts asyncio.StreamReader '
    def __init__(self, stream: asyncio.StreamReader):
        self._stream = stream
    
    async def readuntil(self, separator: bytes = b'\n') -> bytes:
        return await self._stream.readuntil(separator)
    
    async def read(self, count: int = -1) -> bytes:
        return await self._stream.read(count)


class AsyncWriterStream:
    ' Interface for a stream that writes all bytes in data, then returns. '
    async def write(self, data: bytes):
        ' Writes all the bytes provided. '
        raise NotImplementedError()


class AsyncBufferedWriterStream(AsyncWriterStream):
    def __init__(self, stream: io.BufferedWriter):
        self._stream = stream

    async def write(self, data: bytes):
        written = 0
        while written < len(data):
            written += self._stream.write(data[written:])


class AsyncIoWriterStream(AsyncWriterStream):
    ' Adapts asyncio.StreamWriter '
    def __init__(self, stream: asyncio.StreamWriter):
        self._stream = stream
    
    async def write(self, data: bytes):
        self._stream.write(data)


class JsonStreamReader:
    ' An adapter to a stream, which allows to read headers and json objects. '
    def __init__(
        self,
        stream: AsyncReaderStream,
        separator: str = ':',
        linebreak: str = '\r\n',
        encoding: str = 'utf-8'):
        self._stream = stream
        self._separator = separator
        self._linebreak = bytes(linebreak, encoding)
        self._encoding = encoding
    
    async def header(self) -> Dict[str, str]:
        ''' Reads a header from stream until the terminator line is reached.
            Raises an EOFError if eof is encountered during read.
        Returns:
            Dictionary of string with the name of the header option
            to a string with the value of the header option.
        '''
        header = {}
        while True:
            log.debug('Start reading until linebreak (%s).', self._linebreak)
            line: bytes = await self._stream.readuntil(self._linebreak)
            if not line:
                log.debug('Stream reader header encountered end of file.')
                raise EOFError()
            if line == self._linebreak:
                log.debug('Stream reader header terminator received.')
                return header
            log.debug('Line received: "%s"', line.strip())
            line = line.decode(self._encoding)
            parts = line.split(self._separator)
            setting, value = map(str.strip, parts)
            log.debug('Setting header setting "%s" to "%s"', setting, value)
            header[setting.lower()] = value

    async def read(self, header: Dict[str, str]) -> Union[dict, list, str, float, int, bool, None]:
        ''' Reads data according to the header from stream and parses the content as json and returns it.
            If eof is encountered while reading, an EOFError is raised.
            May raise unicode decode or json decode errors if the messages are invalid.
        Parameters:
            header: Dict of header parameters and values.
        Returns:
            A valid json object.
        '''
        content_length: int = int(header['content-length'])
        log.debug('Header content length is %i.', content_length)
        content_type: Optional[str] = header.get('content-type')
        charset: str = 'utf-8'
        if content_type:
            for m in re.finditer(r'(?<!\w)charset=([\w\-]+)', content_type):
                charset = m.group(1)
                log.debug('Setting content charset to "%s', charset)
        log.debug('Json reader reading %i bytes.', content_length)
        content: bytes = await self._stream.read(content_length)
        if not content:
            raise EOFError()
        content = content.decode(charset)
        log.debug('Content received: %s', content)
        obj = json.loads(content)
        log.debug('Json object parsed: %s', obj)
        return obj


class JsonStreamWriter:
    ' An adapater to a writer stream, which allows to write headers and objects serialized with json. '
    def __init__(
        self,
        stream: AsyncWriterStream,
        separator: str = ':',
        linebreak: str = '\r\n',
        encoding: str = 'utf-8'):
        self._stream = stream
        self._separator = bytes(separator, encoding)
        self._linebreak = bytes(linebreak, encoding)
        self._encoding = encoding
        self._content_type = f'application/json; charset={encoding}'
    
    async def send_header(
        self,
        setting: str,
        value: str):
        log.debug('Json writer sending header "%s" with value "%s".', setting, value)
        setting = bytes(setting, self._encoding)
        value = bytes(' ' + value, self._encoding)
        data = setting + self._separator + value + self._linebreak
        await self._stream.write(data)

    async def end_header(self):
        await self._stream.write(self._linebreak)

    async def write(self, o: Any):
        content = json.dumps(o, default=lambda x: x.__dict__)
        content = bytes(content, self._encoding)
        await self.send_header(setting='Content-Length', value=str(len(content)))
        await self.send_header(setting='Content-Type', value=self._content_type)
        await self.end_header()
        log.debug('JsonWriterStream sending content (%i bytes).', len(content))
        await self._stream.write(content)
