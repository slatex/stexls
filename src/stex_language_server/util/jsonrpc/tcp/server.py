from typing import Optional
import asyncio
import logging
from .protocol import JsonRpcTcpProtocol

log = logging.getLogger(__name__)

__all__ = ['Server']

class Server:
    def __init__(self, dispatcher_factory):
        self.__dispatcher_factor = dispatcher_factory
    
    async def _connect(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        peername = writer.get_extra_info('peername')
        log.info('Server incoming connection from %s.', peername)
        protocol = JsonRpcTcpProtocol(reader, writer)
        dispatcher = self.__dispatcher_factor(protocol)
        protocol.set_dispatcher(dispatcher)
        try:
            await protocol.run_until_finished()
        finally:
            await protocol.close()
            log.info('Connection to client %s closed.', peername)

    async def serve_forever(
        self, host: str = 'localhost', port: int = 0, started: Optional[asyncio.Future] = None):
        server = await asyncio.start_server(
            self._connect, host, port)
        info = server.sockets[0].getsockname()
        log.info('Started server at %s', info)
        if started is not None:
            log.debug('Signaling that server started.')
            started.set_result(True)
        async with server:
            await server.serve_forever()
        log.info('Server %s serve_forever() finished.', info)
