''' This is the entrypoint for the language server.
The server can be used by using tcp sockets or
it can simply communicate with another process using
stdin and stdout. After the starver has started,  '''
from typing import Pattern
import logging
import asyncio
import pickle
import re
from tqdm import tqdm
from pathlib import Path

from stexls.util.cli import Cli, command, Arg
from stexls.util.vscode import *
from stexls.compiler import Linker
from stexls.lsp.server import Server

log = logging.getLogger(__name__)

@command(
    root=Arg(type=Path, help="Root directory. Required to resolve imports."),
    file_pattern=Arg('--file-pattern', '-f', default='**/*.tex', type=str, help='Glob pattern of files to add to watchlist.'),
    ignore=Arg('--ignore', '-i', default=None, type=re.compile, help='Regex pattern that if a file path contains this, it will not be watched for changes.'),
    progress_indicator=Arg('--progress-indicator', '-p', action='store_true', help='Enables printing of a progress bar to stderr during update.'),
    no_use_multiprocessing=Arg('--no-use-multiprocessing', '-n', action='store_true', help='If specified, disables multiprocessing completely.'),
    no_cache=Arg('--no-cache', action='store_true', help="Disables cache usage."),
    format=Arg('--format', '-F', help='Formatter for the diagnostics. Defaults to "{file}:{line}:{column} {severity} - {message}".'),
    tagfile=Arg('--tagfile', '-t', const=Path('./tags'), action='store', default=None, nargs='?', type=Path, help='Optional name for a vim tagfile. If no argument is specified "./tags" will be used. Defaults to no tagfile generated.'),
    loglevel=Arg('--loglevel', '-l', default='error', choices=['error', 'warning', 'info', 'debug'], help='Logger loglevel. Defaults to "error".'),
    logfile=Arg('--logfile', '-L', default='/tmp/stexls.log', type=Path, help='Optional path to a logfile. Defaults to "/tmp/stexls.log".')
)
async def linter(
    root: Path,
    file_pattern: 'glob' = '**/*.tex',
    ignore: Pattern = None,
    progress_indicator: bool = False,
    no_use_multiprocessing: bool = False,
    no_cache: bool = False,
    format: str = '{file}:{line}:{column} {severity} - {message}',
    tagfile: Path = None,
    loglevel: str = 'error',
    logfile: Path = '/tmp/stexls.log'):
    """ Run the language server in linter mode. In this mode only diagnostics and progress are printed to stdout. """

    logging.basicConfig(
        filename=logfile,
        level=getattr(logging, loglevel.upper()))
    
    root = root.expanduser().resolve().absolute()

    log.debug('Setting linker root to "%s"', root)

    cache = root / 'stexls-cache.bin'

    log.debug('Linker cache at "%s"', cache)

    linker = None
    if not no_cache and cache.is_file():
        log.info('Loading linker from cache')
        try:
            with open(cache, 'rb') as fd:
                linker = pickle.load(fd)
        except:
            log.exception('Failed to load state from cachefile "%s"', cache)

    if linker is None:
        log.info('No cached linker found or an exception occured: Creating new linker')
        linker = Linker(root, file_pattern=file_pattern, ignore=ignore)

    def progressfn(it, title):
        log.debug('Progress "%s":%i', title, len(it))
        if progress_indicator:
            it = tqdm(it)
            it.set_description(title)
        return it

    log.info('Updating linker...')
    linker.update(progressfn=progressfn, use_multiprocessing=not no_use_multiprocessing)

    if not no_cache:
        with open(cache, 'wb') as fd:
            log.info('Dumping linker cache to "%s"', cache)
            pickle.dump(linker, fd)

    log.debug('Dumping diagnostics of %i objects.', len(linker.objects))
    for path, objects in linker.objects.items():
        for object in objects:
            link = linker.links.get(object, object)
            if link.errors:
                for loc, errs in link.errors.items():
                    for err in errs:
                        print(
                            format.format(
                                file=str(loc.path),
                                line=loc.range.start.line + 1,
                                column=loc.range.start.character + 1,
                                severity=type(err).__name__,
                                message=str(err)))

@command(
    transport_kind=Arg('--transport-kind', '-t', choices=['ipc', 'tcp'], help='Which transport protocol to use. Choices are "ipc" or "tcp". Default is "ipc".'),
    host=Arg('--host', '-H', help='Hostname to bind server to. Defaults to "localhost".'),
    port=Arg('--port', '-p', help='Port number to bind server to. Defaults to 0'),
    loglevel=Arg('--loglevel', '-l', default='error', choices=['error', 'warning', 'info', 'debug'], help='Logger loglevel. Defaults to "error".'),
    logfile=Arg('--logfile', '-L', default='/tmp/stexls.log', type=Path, help='Optional path to a logfile. Defaults to "/tmp/stexls.log"'),
)
async def lsp(
    transport_kind: str = 'ipc',
    host: str = 'localhost',
    port: int = 0,
    loglevel: str = 'error',
    logfile: Path = '/tmp/stexls.log'):
    ' Start the server using stdin and stdout as communication ports. '
    logging.basicConfig(
        filename=logfile,
        level=getattr(logging, loglevel.upper()))
    if transport_kind == 'ipc':
        _, connection = await Server.open_ipc_connection()
    elif transport_kind == 'tcp':
        _, connection = await Server.open_connection(host=host, port=port)
    await connection


if __name__ == '__main__':
    cli = Cli([linter, lsp], __doc__)
    asyncio.run(cli.dispatch())