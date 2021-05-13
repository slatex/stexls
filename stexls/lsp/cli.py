import logging
from asyncio import Task
from pathlib import Path
from typing import Literal, Tuple

from .server import Server


async def lsp(
        transport_kind: Literal['ipc', 'tcp'] = 'ipc',
        host: str = 'localhost',
        port: int = 0,
        loglevel: Literal['critical', 'error', 'info', 'debug'] = 'error',
        logfile: Path = Path('stexls.log')) -> Tuple[Server, Task]:
    """ Starts the language server in either ipc or tcp mode.

    Parameters:
        transport_kind: Mode of transportation to use.
        host: Host for "tcp" transport. Defaults to localhost.
        port: Port for "tcp" transport. Defaults to 0. 0 will bind the server to any free port.
        loglevel: Loglevel. Choices are critical, error, warning, info and debug.
        logfile: File to which logs are written.

    Returns:
        Awaitable task.
    """
    if logfile:
        logfile.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=logfile,
        level=getattr(logging, loglevel.upper()))
    if transport_kind == 'ipc':
        server, connection = await Server.open_ipc_connection()
    elif transport_kind == 'tcp':
        server, connection = await Server.open_connection(host=host, port=port)
    assert isinstance(server, Server)
    return server, connection
