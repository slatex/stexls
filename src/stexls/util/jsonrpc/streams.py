""" This module implements streams which read a json string or write a json string. """
from typing import Union, Any, Dict, List, Optional, BinaryIO, Callable
import asyncio
import re
import json
from socket import socket
from select import select
from .core import RequestObject, NotificationObject, MessageObject, ResponseObject, ErrorCodes, ErrorObject

__all__ = [
    'JsonReader',
    'JsonWriter',
    'JsonStreamReader',
    'JsonBinaryWriter',
    'JsonSocketReader',
    'AsyncIoJsonReader',
]


class JsonReader:
    " An interface for a stream which reads from a stream and parses it as json. "
    async def read_json(self) -> Any:
        """ Reads a json object from stream.

        Raises:
            json.JSONDecodeError: Error if something non-deserializable is received.

        Returns:
            Any: A parsed json object or None if EOF encountered.
        """
        raise NotImplementedError()


class JsonWriter:
    " An interface for a stream which writes json to a stream by serializing any object. "
    def write_json(self, o: Any):
        """ Writes any json parsable object.

        Raises:
            json.JSONDecode[summary]Error: Error if something non-serializable needs to be sent.

        Args:
            o (Any): Json parsable object
        """
        raise NotImplementedError()


class JsonStreamReader(JsonReader):
    " Implements the json stream reader "
    def __init__(
        self,
        stream: BinaryIO,
        linebreak: str = '\r\n',
        encoding: str = 'utf-8'):
        self.stream = stream
        self._linebreak = bytes(linebreak, encoding)
        self._encoding = encoding

    async def read_headers(self) -> Dict[str, str]:
        """Reads headers until empty line is reached.

        Returns:
            Dict[str, str]: Dictionary of headers and their values.
        """
        headers = {}
        loop = asyncio.get_event_loop()
        while True:
            line = await loop.run_in_executor(None, self.stream.readline)
            if not line:
                return None
            if line == self._linebreak:
                return headers
            line: str = line.decode(encoding=self._encoding, errors='strict')
            header, value = line.split(':', maxsplit=1)
            headers[header.strip().lower()] = value.strip()

    async def read_json(self) -> Any:
        """ Reads json object from a binary stream.

        Expects at least thet Content-Length header with the number of bytes needed to decode
        the json object. Optionally a Content-Type header for charset.

        Raises:
            ValueError: Invalid header or content.

        Returns:
            Any: Parsed json object or None if EOF reached.
        """
        header: Dict[str, str] = await self.read_headers()
        if not header:
            return None
        charset = self._encoding
        if 'content-length' not in header:
            raise ValueError('Invalid header: Content-Length not specified.')
        content_length = header['content-length']
        if not content_length.isdigit():
            raise ValueError(f'Invalid Content-Length: "{content_length}"')
        content_length = int(content_length)
        if 'content-type' in header:
            match = re.fullmatch(r'(\S+);\s*charset=(\S+)', header['content-type'])
            if match is not None:
                content_type, charset = match.groups()
                if content_type != 'application/json':
                    raise ValueError(f'Invalid Content-Type: {content_type}')
        loop = asyncio.get_event_loop()
        content = b''
        while True:
            tmp = await loop.run_in_executor(None, self.stream.read, content_length - len(content))
            if not tmp:
                return None
            content += tmp
            if len(content) == content_length:
                break
        content = content.decode(charset, errors='strict')
        return json.loads(content)


class JsonBinaryWriter(JsonWriter):
    ' Writes binary json data. '
    def __init__(
        self,
        write: Callable[[bytes], None],
        linebreak: str = '\r\n',
        charset: str = 'utf-8',
        encoding: str = 'utf-8'):
        self.write = write
        self._linebreak = linebreak
        self._charset = charset
        self._encoding = encoding

    def send_header(self, header: str, value: str):
        content = f'{header}: {value}{self._linebreak}'
        header_bytes = bytes(content, self._encoding)
        self.write(header_bytes)

    def end_header(self):
        self.write(bytes(self._linebreak, self._encoding))

    def write_json(self, o: Any):
        content = json.dumps(o, default=lambda x: x.__dict__)
        content = bytes(content, self._charset)
        self.send_header('Content-Length', str(len(content)))
        self.send_header('Content-Type', f'application/json; charset={self._charset}')
        self.end_header()
        self.write(content)


class JsonSocketReader(JsonStreamReader):
    " Extends the json stream reader to accept sockets as streams. "
    def __init__(
        self,
        sock: socket,
        poll_freq: float = 1.0,
        linebreak: str = '\r\n',
        encoding: str = 'utf-8'):
        super().__init__(self, linebreak, encoding)
        self.__sock = sock
        self.__poll_freq = poll_freq
        self.__buffer = b''

    def poll(self):
        " Poll the socket until data can be read and add it to the buffer. "
        while True:
            print('Waiting for data...')
            ready, _, err = select([self.__sock], [], [self.__sock], self.__poll_freq)
            if err:
                raise RuntimeError(err)
            if ready:
                break
        data = self.__sock.recv(1024)
        if not data:
            raise EOFError()
        print('data read:', data)
        self.__buffer += data

    def readline(self, *args):
        " Polls the socket until a line can be read. "
        while self._linebreak not in self.__buffer:
            self.poll()
        line, self.__buffer = self.__buffer.split(self._linebreak, maxsplit=1)
        return line + self._linebreak

    def read(self, n: int = -1):
        " Polls the socket until EOF is reached if n < 0, or until the buffer has n many bytes. Then returns the polled data. "
        if n < 0:
            try:
                while True:
                    self.poll()
            except EOFError:
                data = self.__buffer
                self.__buffer = b''
                return data
        else:
            while len(self.__buffer) < n:
                self.poll()
            data, self.__buffer = self.__buffer[:n], self.__buffer[n:]
            return data


class AsyncIoJsonReader(JsonReader):
    def __init__(
        self, stream: asyncio.StreamReader, linebreak: str = '\r\n', encoding: str = 'utf-8'):
        self.stream = stream
        self._linebreak = linebreak.encode(encoding)
        self._encoding = encoding

    async def read_headers(self):
        headers: Dict[str, str] = {}
        while True:
            line = await self.stream.readuntil(self._linebreak)
            if not line:
                return None
            if line == self._linebreak:
                return headers
            line = line.decode(self._encoding)
            header, value = line.split(':')
            headers[header.strip().lower()] = value.strip()

    async def read_json(self):
        headers: Dict[str, str] = await self.read_headers()
        if headers is None:
            return None
        if 'content-length' not in headers:
            raise ValueError('Invalid header: Content-Length missing.')
        content_length = headers['content-length']
        if not content_length.isdigit():
            raise ValueError(f'Invalid Content-Length value: {content_length}')
        charset = 'utf-8'
        if 'content-type' in headers:
            match = re.fullmatch(r'(\S+);\s*charset=(\S+)', headers['content-type'])
            if match is not None:
                content_type, charset = match.groups()
                if content_type != 'application/json':
                    raise ValueError(f'Invalid Content-Type: {content_type}')
        content_length = int(content_length)
        try:
            content = await self.stream.readexactly(content_length)
        except asyncio.IncompleteReadError:
            return None
        content = content.decode(charset)
        return json.loads(content)
