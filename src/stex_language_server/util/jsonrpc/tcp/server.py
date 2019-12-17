import asyncio
import logging
from .protocol import JsonRpcProtocol

log = logging.getLogger(__name__)

__all__ = ['Server']

class Server(JsonRpcProtocol):
    async def serve_forever(
        self, host: str = 'localhost', port: int = 0):
        server = await asyncio.start_server(
            self.on_connect, host, port)
        info = server.sockets[0].getsockname()
        log.info('Started server at %s', info)
        try:
            async with server:
                await server.serve_forever()
        finally:
            await self._dispatcher.close()
        log.debug('Server %s serve_forever() finished.', info)
    