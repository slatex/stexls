from typing import Optional
import asyncio
import logging
from .protocol import JsonRpcTcpProtocol

log = logging.getLogger(__name__)

__all__ = ['Client']

class Client:
    def __init__(self, dispatcher_factory):
        self.__dispatcher_factor = dispatcher_factory
        self.__running_task = None
    
    def close(self):
        ' Cancels the underlying tasks that runs the client. '
        self.__running_task.cancel()
    
    async def __run_until_finished(self, peername):
        ' Wrapper that encapsulates the run operation as a single coro object. '
        try:
            await self.__protocol.run_until_finished()
        finally:
            await self.__protocol.close()
            log.info('Connection to server at %s closed.', peername)
    
    async def open_connection(
        self, host: str = 'localhost', port: int = 0):
        ''' Opens a connection to a server and returns the dispatcher
            that was created for this connection. '''
        reader, writer = await asyncio.open_connection(host, port)
        peername = writer.get_extra_info('peername')
        log.info('Client connected to %s', peername)
        self.__protocol = JsonRpcTcpProtocol(reader, writer)
        dispatcher = self.__dispatcher_factor(self.__protocol)
        self.__protocol.set_dispatcher(dispatcher)
        self.__running_task = asyncio.create_task(self.__run_until_finished(peername))
        return dispatcher
