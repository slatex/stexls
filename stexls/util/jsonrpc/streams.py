from typing import Any, Dict
import asyncio
import re
import json

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
            newline: str = '\n'):
        """ Initializes the json stream with underlying stream reader and writer.

        Args:
            reader: Input stream.
            writer: Output stream.
            encoding: Encoding to use for header.
            charset: Encoding to use for body content. Same as encoding if None.
            newline: Which character should be used to represent newlines.
        """
        self.reader = reader
        self.writer= writer
        self.encoding = encoding
        self.charset = charset
        self.newline = newline.encode(charset or encoding)

    def write_json(self, o: Any):
        ' Serializes the object with json and writes it to the underlying stream writer. '
        serialized = json.dumps(o, default=lambda x: x.__dict__)
        charset = self.charset or self.encoding
        content = serialized.encode(charset)
        length_header = f'Content-Length: {len(content)}'.encode(self.encoding)
        type_header = f'Content-Type: application/json; charset={charset}'.encode(self.encoding)
        self.writer.write(length_header + self.newline)
        self.writer.write(type_header + self.newline)
        self.writer.write(self.newline + content)

    async def read_json(self) -> Any:
        ' Read a json object from stream, parse and return it. '
        headers: Dict[str, str] = await self.read_headers()
        content_length = headers.get('content-length')
        if not content_length or not content_length.isdigit():
            raise ValueError('Invalid header: Content-Length missing or malformed.')
        content_length = int(content_length)
        content_type = headers.get('content-type')
        charset = self.charset
        if content_type:
            match = re.match(r'(\w+/\w+)(?:;\s*charset=(\S+))?', content_type)
            if match:
                media_type= match.group(1)
                charset = match.group(2) or charset
                if media_type != 'application/json':
                    raise ValueError(f'Expected media type "application/json", received: "{media_type}"')
        content = await self.reader.readexactly(content_length)
        if not content:
            raise EOFError()
        serialized = content.decode(charset)
        return json.loads(serialized)

    async def read_headers(self) -> Dict[str, str]:
        ' Reads a dict of headers to header values from stream. '
        headers: Dict[str, str] = {}
        while True:
            line = await self.reader.readline()
            if line == self.newline:
                return headers
            if not line:
                raise EOFError()
            line = line.decode(self.encoding)
            try:
                header, value = line.split(':', maxsplit=1)
            except ValueError as e:
                raise ValueError(f'Invalid line format in line "{line.strip()}": Missing ":" character.') from e
            headers[header.strip().lower()] = value.strip()

