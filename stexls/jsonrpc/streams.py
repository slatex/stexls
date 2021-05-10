import asyncio
import json
import re
from typing import Any, Dict

__all__ = ['JsonStream']


class JsonStream:
    """ A JsonStream implements a modified stream interface
    with read_json() and write_json() which allows to deserialize and
    deserialize objects using json.
    """

    def __init__(
            self,
            reader: asyncio.StreamReader,
            writer: asyncio.StreamWriter,
            encoding: str = 'utf-8',
            charset: str = None,
            newline: str = '\r\n',
            with_content_type: bool = False):
        """ Initializes the json stream with underlying stream reader and writer.

        Args:
            reader: Input stream.
            writer: Output stream.
            encoding: Encoding to use for header.
            charset: Encoding to use for body content. Same as encoding if None.
            newline: Which character should be used to represent newlines.
            with_content_type: Serialize with Content-Type header
        """
        self.reader = reader
        self.writer = writer
        self.encoding = encoding
        self.charset = charset or encoding
        self.newline = newline.encode(charset or encoding)
        self.with_content_type = with_content_type

    def close(self):
        self.writer.close()

    def write_json(self, json_object: Any):
        ' Serializes the object with json and writes it to the underlying stream writer. '
        def serializer(child):
            try:
                if hasattr(child, 'to_json') and callable(child.to_json):
                    return child.to_json()
                elif hasattr(child, 'serialize') and callable(child.serialize):
                    return child.serialize()
            except Exception:
                pass
            return dict(child.__dict__.items())
        serialized = json.dumps(json_object, default=serializer)
        content = serialized.encode(self.charset)
        length_header = f'Content-Length: {len(content)}'.encode(self.encoding)
        if self.with_content_type:
            type_header = f'Content-Type: application/json; charset={self.charset}'.encode(
                self.encoding)
        self.writer.write(length_header + self.newline)
        if self.with_content_type:
            self.writer.write(type_header + self.newline)
        self.writer.write(self.newline + content)

    async def read_json(self) -> Any:
        r''' Read a json object from stream, parse and return it.

        Waits for bytes from stream, continuously attempting to read a header object until
        the empty header is received.

        After the empty header is received of the form "\r\n\r\n", start reading
        as many bytes as the "content-length" header value.
        Raises ValueError if "content-length" was not received.
        '''
        headers: Dict[str, str] = await self.read_headers()
        content_length_header = headers.get('content-length')
        if not content_length_header or not content_length_header.isdigit():
            raise ValueError(
                'Invalid header: Content-Length missing or malformed.')
        content_length = int(content_length_header)
        content_type = headers.get('content-type')
        charset = self.charset
        if content_type:
            match = re.match(r'(\w+/\w+)(?:;\s*charset=(\S+))?', content_type)
            if match:
                media_type = match.group(1)
                charset = match.group(2) or charset
                if media_type != 'application/json':
                    raise ValueError(
                        f'Expected media type "application/json", received: "{media_type}"')
        content = await self.reader.readexactly(content_length)
        if not content:
            raise EOFError()
        serialized = content.decode(charset)
        return json.loads(serialized)

    async def read_headers(self) -> Dict[str, str]:
        r''' Reads a dict of headers to header values from stream.

        A header is a line of the following HTTP like format:

        <header name>: <value>\r\n


        where the header name is a string separated by a colon from the value.
        The line needs to end with "\r\n".
        '''
        headers: Dict[str, str] = {}
        while True:
            raw_line: bytes = await self.reader.readline()
            if raw_line == self.newline:
                return headers
            if not raw_line:
                raise EOFError()
            line = raw_line.decode(self.encoding)
            try:
                header, value = line.split(':', maxsplit=1)
            except ValueError as e:
                raise ValueError(
                    f'Invalid line format in line "{line.strip()}": Missing ":" character.') from e
            headers[header.strip().lower()] = value.strip()
