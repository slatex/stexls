from typing import Optional
import asyncio
import logging
from .protocol import JsonRpcProtocol

log = logging.getLogger(__name__)

__all__ = ['Server']

class Server:
    def __init__(self, protocol_factory):
        self._protocol_factory = protocol_factory
        self._started = asyncio.Future()
        self._running = False
    
    async def started(self):
        ''' A coroutine that only returns after the server has started.
        Returns:
            Tuple of (host, port) on which the server is running. '''
        return await self._started

    async def _connect(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        peername = writer.get_extra_info('peername')
        log.info('Server incoming connection from %s.', peername)
        protocol = self._protocol_factory(reader, writer)
        try:
            await protocol.run_until_finished()
        except Exception:
            log.exception('Server connection run loop to %s was interrupted by an exception.', peername)
        finally:
            log.info('Connection to client %s closed.', peername)

    async def serve_forever(
        self, host: str = 'localhost', port: int = 0):
        if self._running:
            raise ValueError('Server is already running.')
        self._running = True
        try:
            server = await asyncio.start_server(
                self._connect, host, port)
            info = server.sockets[0].getsockname()
            log.info('Started server at %s', info)
            self._started.set_result(info)
            async with server:
                await server.serve_forever()
        finally:
            self._started.cancel()
            self._running = False
        log.info('Server %s serve_forever() finished.', info)
