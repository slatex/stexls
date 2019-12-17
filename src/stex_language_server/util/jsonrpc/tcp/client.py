import asyncio
import logging
from .protocol import JsonRpcProtocol

log = logging.getLogger(__name__)

__all__ = ['Client']

class Client(JsonRpcProtocol):
    async def open_connection(
        self, host: str = 'localhost', port: int = 0):
        log.info('Connecting client to %s:%i', host, port)
        reader, writer = await asyncio.open_connection(host, port)
        try:
            await self.on_connect(reader, writer)
        finally:
            await self._dispatcher.close()
        log.info('Client connection to %s:%i finished.', host, port)
