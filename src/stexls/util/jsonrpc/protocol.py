from typing import Dict, Any
import re
import logging
import asyncio
import json

log = logging.getLogger(__name__)

__all__ = ['JsonProtocol']

class JsonProtocol(asyncio.Protocol):
    def __init__(self, encoding: str = 'utf-8', newline: str = '\r\n'):
        self.encoding = encoding
        self.newline = newline.encode(encoding)
        self.chunk_queue = asyncio.Queue()
        self.buffer = b''
        self.transport = None
        self.peername = None

    def send_json(self, o: Any):
        serialized = json.dumps(o, default=lambda x: x.__dict__)
        content = serialized.encode(self.encoding)
        content_length = f'Content-Length: {len(content)}'.encode(self.encoding)
        content_type = f'Content-Type: application/json; charset={self.encoding}'.encode(self.encoding)
        message = content_length + self.newline + content_type + self.newline + self.newline + content
        log.debug('Sending %i (\\w headers %i) bytes to "%s"', len(content), len(message), self.peername)
        self.transport.write(message)

    async def read_json(self) -> Any:
        headers: Dict[str, str] = await self.read_headers()
        log.debug('Header received: %s', headers)
        content_length = headers.get('content-length')
        if not content_length or not content_length.isdigit():
            raise ValueError('Invalid header: Content-Length missing or malformed.')
        content_length = int(content_length)
        content_type = headers.get('content-type')
        charset = 'utf-8'
        if content_type:
            match = re.match(r'(\w+/\w+)(?:;\s*charset=(\S+))?', content_type)
            if match:
                media_type, charset_ = match.groups()
                charset = charset_ or charset
                if media_type != 'application/json':
                    raise ValueError(f'Expected media type "application/json", received: "{media_type}"')
        log.debug('Waiting for %i bytes of content.', content_length)
        content = await self.readexactly(content_length)
        log.debug('Decoding content using charset=%s', charset)
        serialized = content.decode(charset)
        return json.loads(serialized)

    async def readexactly(self, n: int):
        while len(self.buffer) < n:
            log.debug('Waiting for %i/%i bytes.', len(self.buffer), n)
            await self.accept_chunk()
        data, self.buffer = self.buffer[:n], self.buffer[n:]
        return data

    async def read_headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {}
        while True:
            while self.newline not in self.buffer:
                log.debug('Waiting for header in buffer.')
                await self.accept_chunk()
            line, self.buffer = self.buffer.split(self.newline, maxsplit=1)
            if not line:
                return headers
            line = line.decode(self.encoding)
            header, value = line.split(':', maxsplit=1)
            headers[header.strip().lower()] = value.strip()

    async def accept_chunk(self):
        chunk = await self.chunk_queue.get()
        if chunk is None:
            raise EOFError()
        log.debug('Chunk received (%i bytes).', len(chunk))
        self.buffer += chunk

    def connection_made(self, transport):
        self.transport = transport
        self.peername = transport.get_extra_info('peername')
        log.info('Connected to "%s"', self.peername)

    def data_received(self, data):
        log.debug('Data received (%i bytes).', len(data))
        self.chunk_queue.put_nowait(data)

    def connection_lost(self):
        log.info('Disconnected from "%s"', self.peername)
        self.chunk_queue.put_nowait(None)
