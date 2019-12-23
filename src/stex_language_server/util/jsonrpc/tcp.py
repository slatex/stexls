from typing import Optional, Callable
import asyncio
import logging
from .protocol import JsonRpcProtocol
from .dispatcher import Dispatcher, DispatcherTarget

log = logging.getLogger(__name__)

__all__ = ['open_connection', 'start_server']

async def open_connection(
    dispatcher_factory: Callable[[DispatcherTarget], Dispatcher],
    host: str = 'localhost',
    port: int = 0,
    connection: asyncio.Future = None):
    ''' Creates and connects a client to a given host and port.
    Returns:
        Protocol loop awaitable.
        The created dispatcher can be retrieved by providing and
        awaiting the connection argument.
    '''
    reader, writer = await asyncio.open_connection(host, port)
    peername = writer.get_extra_info('peername')
    protocol = JsonRpcProtocol(reader, writer)
    dispatcher = dispatcher_factory(protocol)
    protocol.set_method_provider(dispatcher)
    log.info('Client connected to %s.', peername)
    if connection:
        connection.set_result(dispatcher)
    try:
        await protocol.run_until_finished()
    finally:
        log.info('Client disconnected from %s.', peername)

async def start_server(
    dispatcher_factory: Callable[[DispatcherTarget], Dispatcher],
    host: str = 'localhost',
    port: int = 0,
    started: asyncio.Future = None,
    connections: asyncio.Queue = None):
    ''' Starts a server at the given host and port.
        Creates a new dispatcher using dispatcher_factory every
        time a new connection is made.
    Returns:
        Server loop awaitable and if given,
        puts the host and port the server is listening at
        into <started>
    '''
    async def connect(r, w):
        peername = w.get_extra_info('peername')
        log.info('Server accepted connection from %s.', peername)
        protocol = JsonRpcProtocol(r, w)
        dispatcher = dispatcher_factory(protocol)
        protocol.set_method_provider(dispatcher)
        closed = asyncio.Future()
        if connections is not None:
            await connections.put({
                'protocol': protocol,
                'dispatcher': dispatcher,
                'peername': peername,
                'closed': closed})
        try:
            await protocol.run_until_finished()
        finally:
            closed.set_result(True)
            log.info('Server connection to %s closed.', peername)
    server = await asyncio.start_server(connect, host, port)
    info = server.sockets[0].getsockname()
    log.info('Server running at jsonrpc://%s:%i', *info)
    if started:
        started.set_result(info)
    async with server:
        await server.serve_forever()
