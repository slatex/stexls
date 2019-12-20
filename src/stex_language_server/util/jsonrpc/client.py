from typing import Optional
import asyncio
import logging
from .protocol import JsonRpcProtocol

log = logging.getLogger(__name__)

__all__ = ['Client']

class Client:
    def __init__(self, dispatcher_factory: type, protocol_factory: type = None):
        self.__dispatcher_factory = dispatcher_factory
        self.__protocol_factory = protocol_factory or JsonRpcProtocol
        self.__running_task = None
    
    def close(self):
        ' Cancels the underlying tasks that runs the client. '
        self.__running_task.cancel()
    
    async def open_connection(
        self, host: str = 'localhost', port: int = 0):
        ''' Opens a connection to a server and returns the dispatcher
            that was created for this connection. '''
        reader, writer = await asyncio.open_connection(host, port)
        peername = writer.get_extra_info('peername')
        log.info('Client connected to %s', peername)
        self.__protocol = self.__protocol_factory(reader, writer)
        dispatcher = self.__dispatcher_factory(self.__protocol)
        self.__running_task = asyncio.create_task(self.__protocol.run_until_finished())
        return dispatcher
