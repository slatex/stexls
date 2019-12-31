''' This module provides helper functions that help creating
json-rpc servers and clients over tcp.
Use open_connection() to create a client and use start_server() to create a server. '''
from typing import Optional, Callable
import asyncio
import logging
from .streams import AsyncIoReaderStream, AsyncIoWriterStream
from .protocol import JsonRpcProtocol
from .dispatcher import Dispatcher

log = logging.getLogger(__name__)

__all__ = ['open_connection', 'start_server']


async def open_connection(
    dispatcher_factory: Callable[[JsonRpcProtocol], Dispatcher],
    host: str = 'localhost', port: int = 0):
    """Connects a client to a given host and port.
    
    Args:
        dispatcher_factory (Callable[[JsonRpcProtocol], Dispatcher]): Factory for a dispatcher for the connection.
        host (str, optional): Server host. Defaults to 'localhost'.
        port (int, optional): Server port. Defaults to 0.
    
    Returns:
        2-Tuple: First item is the dispatcher for the connection.
            Second is the task the client runs on.
    """
    log.info('Connecting to server at %s:%i ...', host, port)
    reader, writer = await asyncio.open_connection(host, port)
    peername = writer.get_extra_info('peername')
    log.info('Client connected to %s.', peername)
    protocol = JsonRpcProtocol(
        AsyncIoReaderStream(reader),
        AsyncIoWriterStream(writer))
    dispatcher = dispatcher_factory(protocol)
    async def client_run_task():
        try:
            log.debug('Starting client protocol loop.')
            await protocol.run_until_finished()
            log.debug('Client loop of %s finished without errors.', peername)
        finally:
            log.info('Client disconnected from %s.', peername)
    task = asyncio.create_task(client_run_task()) 
    return dispatcher, task


async def start_server(
    dispatcher_factory: Callable[[JsonRpcProtocol], Dispatcher],
    host: str = 'localhost',
    port: int = 0):
    """Starts a asyncio tcp server. At the given host and port.
    
    Args:
        dispatcher_factory (Callable[[JsonRpcProtocol], Dispatcher]): A factory for a dispatcher for each new connection.
        host (str, optional): Server host. Defaults to 'localhost'.
        port (int, optional): Server pot. Defaults to 0.
    
    Returns:
        3-Tuple: First is the host and port the server is bound to.
            Second is the asyncio Task the server runs at.
            Third is a list of active connections.
    """
    connections = []
    async def connect(reader, writer):
        peername = writer.get_extra_info('peername')
        log.info('Server accepted connection from %s.', peername)
        protocol = JsonRpcProtocol(
            AsyncIoReaderStream(reader),
            AsyncIoWriterStream(writer))
        connection = dispatcher_factory(protocol)
        connections.append(connection)
        try:
            log.debug('Starting server client loop.')
            await protocol.run_until_finished()
            log.debug('Client loop of %s finished without errors.', peername)
        except:
            log.exception('Server connection to %s closed by exception.')
        finally:
            connections.remove(connection)
            log.info('Server connection to %s closed.', peername)
    log.info('Starting server on %s:%i ...', host, port)
    server = await asyncio.start_server(connect, host, port)
    info = server.sockets[0].getsockname()
    log.info('Server running at jsonrpc://%s:%i', *info)
    async def serving_task():
        try:
            log.debug('Starting server serve_forever() loop.')
            async with server:
                await server.serve_forever()
            log.debug('Server loop finished without errors.')
        finally:
            log.info('Server %s:%i closed.', host, port)
    task = asyncio.create_task(serving_task()) 
    return info, task, connections