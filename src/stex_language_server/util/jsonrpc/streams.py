from typing import Union, Optional, Any
import re
import json
import logging

log = logging.getLogger(__name__)

__all__ = (
    'AsyncReaderStream',
    'JsonStreamReader',
    'WriterStream',
    'JsonStreamWriter'
)

class AsyncReaderStream:
    ' Interface for a stream that can read lines and bytes asynchronously. '
    async def readuntil(self, separator: bytes = b'\n') -> bytes:
        ' Reads data until separator is reached. '
        raise NotImplementedError()

    async def read(self, count: int) -> bytes:
        ' Reads count many bytes from stream and returns them. '
        raise NotImplementedError()


class JsonStreamReader:
    ' An adapter to a stream, which allows to read headers and json objects. '
    def __init__(self, stream: AsyncReaderStream):
        self._stream = stream
    
    async def header(
        self,
        encoding: str = 'utf-8',
        separator: str = ':',
        linebreak: bytes = b'\r\n') -> dict:
        ' Reads a header from stream until the terminator line is reached. '
        header = {}
        while True:
            log.debug('Start reading until linebreak %s', linebreak)
            line: bytes = await self._stream.readuntil(linebreak)
            if not line:
                log.debug('Stream reader header encountered end of file.')
                raise EOFError()
            if line == linebreak:
                log.debug('Stream reader header terminator received.')
                return header
            log.debug('Line received: "%s"', line.strip())
            line = line.decode(encoding)
            parts = line.split(separator)
            setting, value = map(str.strip, parts)
            log.debug('Setting header setting "%s" to "%s"', setting, value)
            header[setting.lower()] = value

    async def read(self, header: dict) -> Union[dict, list, str, float, int, bool, None]:
        ' Reads data according to the header from stream and parses the content as json and returns it. '
        content_length: int = int(header['content-length'])
        log.debug('Header content length is %i.', content_length)
        content_type: Optional[str] = header.get('content-type')
        charset: str = 'utf-8'
        if content_type:
            for m in re.finditer(r'(?<!\w)charset=([\w\-]+)', content_type):
                charset = m.group(1)
        log.debug('Json reader reading %i bytes.', content_length)
        content: bytes = await self._stream.read(content_length)
        log.debug('Decoding content using charset "%s"', charset)
        content = content.decode(charset)
        log.debug('Content read: "%s"', content)
        return json.loads(content)


class WriterStream:
    ' Interface for a stream that writes all bytes in data, then returns. '
    def write(self, data: bytes):
        raise NotImplementedError()


class JsonStreamWriter:
    ' An adapater to a writer stream, which allows to write headers and objects serialized with json. '
    def __init__(self, stream: WriterStream):
        self._stream = stream
    
    def send_header(
        self,
        setting: str,
        value: str,
        separator: str = ':',
        encoding: str = 'utf-8',
        linebreak: bytes = b'\r\n'):
        header = f'{setting}{separator} {value}'
        log.debug('Json writer sending header "%s" with value "%s"', setting, value)
        data = bytes(header, encoding) + linebreak
        self._stream.write(data)

    def end_header(self, linebreak: bytes = b'\r\n'):
        self._stream.write(linebreak)

    def write(
        self,
        o: Any,
        encoding: str = 'utf-8',
        header_encoding: str = None,
        separator: str = ':',
        linebreak: bytes = b'\r\n',
        content_type: str = 'application/json; charset={encoding}'):
        content = json.dumps(o, default=lambda x: x.__dict__)
        content = bytes(content, encoding)
        log.debug(
            'Prepairing header: content-length=%i, encoding=%s, content-type=%s',
            len(content), encoding, content_type)
        self.send_header(
            'Content-Length',
            len(content),
            separator,
            header_encoding or encoding,
            linebreak)
        if content_type:
            self.send_header(
                'Content-Type',
                content_type.format(encoding=encoding, separator=separator, header_encoding=header_encoding),
                separator,
                header_encoding or encoding,
                linebreak)
        self.end_header(linebreak)
        self._stream.write(content)
