from typing import Optional
import asyncio
import logging
from .protocol import JsonRpcProtocol

log = logging.getLogger(__name__)

__all__ = ['Client']

class Client(JsonRpcProtocol):
    async def open_connection(
        self, host: str = 'localhost', port: int = 0, started: Optional[asyncio.Future] = None):
        log.info('Connecting client to %s:%i', host, port)
        reader, writer = await asyncio.open_connection(host, port)
        if started is not None:
            log.debug('Signaling that client opened the connection.')
            started.set_result(True)
        try:
            await self.on_connect(reader, writer)
        finally:
            await self._dispatcher.close()
        log.info('Client connection to %s:%i finished.', host, port)
