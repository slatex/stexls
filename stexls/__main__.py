''' This is the entrypoint for the language server.
The server can be used by using tcp sockets or
it can simply communicate with another process using
stdin and stdout. After the starver has started,  '''
from typing import Pattern
import logging
import asyncio
import pickle
import re
import pkg_resources
from tqdm import tqdm
from pathlib import Path

from stexls.util.cli import Cli, command, Arg
from stexls.util.vscode import *
from stexls.stex import Linker
from stexls.lsp.server import Server

log = logging.getLogger(__name__)


def _read_location(loc: Location):
    ' Opens the file and returns the text at the range of the location. Returns None if the file does not exist or the location can\'t be read. '
    try:
        with open(loc.path, 'r') as fd:
            lines = fd.readlines()
            if loc.range.is_single_line():
                return lines[loc.range.start.line][loc.range.start.character:loc.range.end.character]
            else:
                lines = lines[loc.range.start.line:loc.range.end.line+1]
                return '\n'.join(lines)[loc.range.start.character:-loc.range.end.character]
    except (IndexError, FileNotFoundError):
        log.exception('Failed to read location: "%s"', loc.format_link())
        return None


@command(
    root=Arg(type=Path, help="Root directory. Required to resolve imports."),
    file_pattern=Arg('--file-pattern', '-f', default='**/*.tex', type=str, help='Glob pattern of files to add to watchlist.'),
    ignore=Arg('--ignore', '-i', default=None, type=re.compile, help='Regex pattern that if a file path contains this, it will not be watched for changes.'),
    progress_indicator=Arg('--progress-indicator', '-p', action='store_true', help='Enables printing of a progress bar to stderr during update.'),
    no_use_multiprocessing=Arg('--no-use-multiprocessing', '-n', action='store_true', help='If specified, disables multiprocessing completely.'),
    no_cache=Arg('--no-cache', action='store_true', help="Disables cache usage."),
    format=Arg('--format', '-F', help='Formatter for the diagnostics. Defaults to "{file}:{line}:{column} {severity} - {message}".'),
    tagfile=Arg('--tagfile', '-t', const='tags', action='store', default=None, nargs='?', help='Optional name for a vim tagfile. If no argument is specified "tags" will be used. Defaults to no tagfile generated.'),
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
    """ Run the language server in linter mode.
    
        In this mode only diagnostics and progress are printed to stdout.
    
    Parameters:
        root: Root of stex imports.
        file_pattern: Pattern of files to add.
        ignore: Regex that can be used to ignore certain file patterns.
        progress_indicator: Enables a progress bar being printed to stderr.
        no_use_multiprocessing: Disables multiprocessing.
        no_cache: Disables cache.
        format: Format of the diagnostics. Defaults to "{file}:{line}:{column} {severity} - {message}".
        tagfile: Optional name of the generated tagfile. If None, no tagfile will be generated.
        loglevel: Server loglevel. Choices are critical, error, warning, info and debug.
        logfile: File to which logs will be logged. Defaults to "/tmp/stexls.log"

    Returns:
        Awaitable task.
    """

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

    if tagfile:
        trans = str.maketrans({'-': r'\-', ']': r'\]', '\\': r'\\', '^': r'\^', '$': r'\$', '*': r'\*', '.': r'\,', '\t': ''})
        lines = []
        for path, objects in linker.objects.items():
            for object in objects:
                for id, symbols in object.symbol_table.items():
                    for symbol in symbols:
                        keyword = symbol.identifier.identifier.replace('\t', '')
                        file = symbol.location.path.as_posix()
                        text = _read_location(symbol.location)
                        if not text:
                            continue
                        pattern = text.translate(trans)
                        lines.append(f'{keyword}\t{file}\t/{pattern}\n')
                        qkeyword = symbol.qualified_identifier.identifier.replace('.', '?')
                        if qkeyword != keyword:
                            lines.append(f'{qkeyword}\t{file}\t/{pattern}\n')
        try:
            tagfile_path = (root/tagfile).as_posix()
            log.info('Writing tagfile to "%s" (%i tags)', tagfile_path, len(lines))
            with open(tagfile_path, 'w') as fd:
                fd.writelines(sorted(lines))
        except FileExistsError:
            log.exception('Failed to write tagfile')

        del lines

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
    transport_kind=Arg('--transport-kind', '-t', choices=['ipc', 'tcp'], help='Which transport protocol to use. Choices are "ipc" or "tcp".'),
    host=Arg('--host', '-H', help='Hostname to bind server to.'),
    port=Arg('--port', '-p', help='Port number to bind server to.'),
    loglevel=Arg('--loglevel', '-l', default='error', choices=['error', 'warning', 'info', 'debug'], help='Logger loglevel.'),
    logfile=Arg('--logfile', '-L', default='/tmp/stexls.log', type=Path, help='Optional path to a logfile.'),
)
async def lsp(
    transport_kind: str = 'ipc',
    host: str = 'localhost',
    port: int = 0,
    loglevel: str = 'error',
    logfile: Path = '/tmp/stexls.log'):
    """ Starts the language server in either ipc or tcp mode.

    Parameters:
        transport_kind: Mode of transportation to use.
        host: Host for "tcp" transport. Defaults to localhost.
        port: Port for "tcp" transport. Defaults to 0. 0 will bind the server to any free port.
        loglevel: Loglevel. Choices are critical, error, warning, info and debug.
        logfile: File to which logs are written. Defaults to /tmp/stexls.log

    Returns:
        Awaitable task.
    """
    logging.basicConfig(
        filename=logfile,
        level=getattr(logging, loglevel.upper()))
    if transport_kind == 'ipc':
        _, connection = await Server.open_ipc_connection()
    elif transport_kind == 'tcp':
        _, connection = await Server.open_connection(host=host, port=port)
    await connection


if __name__ == '__main__':
    cli = Cli(commands=[linter, lsp], description=__doc__, version=pkg_resources.require('stexls')[0].version)
    asyncio.run(cli.dispatch())