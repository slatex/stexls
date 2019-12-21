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
    started: asyncio.Future = None):
    async def connect(r, w):
        peername = w.get_extra_info('peername')
        log.info('Server accepted connection from %s.', peername)
        protocol = JsonRpcProtocol(r, w)
        protocol.set_method_provider(dispatcher_factory(protocol))
        try:
            await protocol.run_until_finished()
        finally:
            log.info('Server connection to %s closed.', peername)
    server = await asyncio.start_server(connect, host, port)
    info = server.sockets[0].getsockname()
    log.info('Server running at jsonrpc://%s:%i', *info)
    if started:
        started.set_result(info)
    async with server:
        await server.serve_forever()
