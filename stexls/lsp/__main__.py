''' This is the entrypoint for the language server.
The server can be used by using tcp sockets or
it can simply communicate with another process using
stdin and stdout. After the starver has started,  '''
import logging
import asyncio
from stexls.util.cli import Cli, command, Arg

log = logging.getLogger(__name__)


@command(
    host=Arg(help='Hostname to bind server to.'),
    port=Arg(help='Port number to bind server to.'),
    loglevel=Arg(default='error', choices=['error', 'warning', 'info', 'debug'], help='Logger loglevel.'),
)
async def tcp(host: str = 'localhost', port: int = 0, loglevel: str = 'error'):
    ' Starts the server by creating a tcp server. '
    logging.basicConfig(level=getattr(logging, loglevel.upper()))


@command(
    loglevel=Arg(default='error', choices=['error', 'warning', 'info', 'debug'], help='Logger loglevel.'),
)
async def stdio(loglevel: str = 'error'):
    ' Start the server using stdin and stdout as communication ports. '
    logging.basicConfig(level=getattr(logging, loglevel.upper()))


if __name__ == '__main__':
    cli = Cli([tcp, stdio], __doc__)
    asyncio.run(cli.dispatch())