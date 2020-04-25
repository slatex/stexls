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
from stexls.util.workspace import Workspace
from stexls.stex import Compiler, Linker
from stexls.lsp import Server

log = logging.getLogger(__name__)


@command(
    files=Arg(type=Path, nargs='+', help='List of files for which to generate diagnostics.'),
    root=Arg(required=True, type=Path, help="Root directory. Required to resolve imports."),
    check_modified=Arg('--check-modified', '-m', action='store_true', help='Only create diagnostics for modified files.'),
    include=Arg('--include', '-I', nargs='+', type=re.compile, help='List of regex patterns. Only files that match ANY of these patterns will be included.'),
    ignore=Arg('--ignore', '-i', nargs='+', type=re.compile, help='List of regex pattern. All files that match ANY of these patterns will be excluded.'),
    verbose=Arg('--verbose', '-v', action='store_true', help='If enabled, instead of only printing errors, this will print all infos about each input file.'),
    progress_indicator=Arg('--progress-indicator', '-p', action='store_true', help='Enables printing of a progress bar to stderr during update.'),
    no_use_multiprocessing=Arg('--no-use-multiprocessing', '-n', action='store_true', help='If specified, disables multiprocessing completely.'),
    format=Arg('--format', '-F', help='Formatter for the diagnostics.'),
    tagfile=Arg('--tagfile', '-t', const='tags', action='store', nargs='?', help='Optional name for a vim tagfile. If used without a value "tags" will be used. If not specified, no tagfile will be generated.'),
    loglevel=Arg('--loglevel', '-l', choices=['error', 'warning', 'info', 'debug'], help='Logger loglevel.'),
    logfile=Arg('--logfile', '-L', type=Path, help='Optional path to a logfile.')
)
async def linter(
    files: List[Path],
    root: Path = '.',
    check_modified: bool = False,
    include: List[Pattern] = None,
    ignore: List[Pattern] = None,
    verbose: bool = False,
    progress_indicator: bool = False,
    no_use_multiprocessing: bool = False,
    format: str = '{file}:{line}:{column} {severity} - {message}',
    tagfile: str = None,
    loglevel: str = 'error',
    logfile: Path = Path('stexls.log')):
    """ Run the language server in linter mode.
    
        In this mode only diagnostics and progress are printed to stdout.
    
    Parameters:
        root: Root of stex imports.
        files: List of input files. While dependencies are compiled, only these specified files will generate diagnostics.
        check_modified: If enabled, only modified files will generate diagnostics.
        include: List of regex patterns. Only files that match ANY of these patterns will be included.
        ignore: List of regex pattern. All files that match ANY of these patterns will be excluded.
        progress_indicator: Enables a progress bar being printed to stderr.
        verbose: If enabled, instead of only printing errors, all infos about each input file will be printed.
        no_use_multiprocessing: Disables multiprocessing.
        format: Format of the diagnostics. Defaults to "{file}:{line}:{column} {severity} - {message}".
        tagfile: Optional name of the generated tagfile. If None, no tagfile will be generated.
        loglevel: Server loglevel. Choices are critical, error, warning, info and debug.
        logfile: File to which logs will be logged. Defaults to "/tmp/stexls.log"

    Returns:
        Awaitable task.
    """
    root = root.expanduser().resolve().absolute()

    settings_dir = root / '.stexls'

    settings_dir.mkdir(exist_ok=True)

    if not logfile.is_absolute():
        logfile = settings_dir / logfile

    logging.basicConfig(
        filename=logfile,
        level=getattr(logging, loglevel.upper()))

    log.debug('Setting linker root to "%s"', root)

    outdir = settings_dir / 'objects'

    outdir.mkdir(exist_ok=True)

    log.debug('Compiler outdir at "%s"', outdir)

    def progressfn(title):
        def wrapper(it):
            log.debug('Progress "%s":%i', title, len(it))
            if progress_indicator:
                it = tqdm(it)
                it.set_description(title)
            return it
        return wrapper

    files = list(map(Path.absolute, files))
    workspace = Workspace(root)
    workspace.ignore = ignore
    workspace.include = include
    wsfiles = workspace.files
    files = list(file for file in files if file in wsfiles)
    compiler = Compiler(workspace, outdir)
    if check_modified:
        files = compiler.modified(files)
    objects = compiler.compile(files, progressfn('Compiling'), not no_use_multiprocessing)
    linker = Linker(root)
    links = linker.link(objects, compiler.modules, progressfn, not no_use_multiprocessing)

    if tagfile:
        log.debug('Creating tagfile at "%s"', root / tagfile)
        compiler.create_tagfile(tagfile)

    log.debug('Dumping diagnostics of %i objects.', len(links))
    for object in links.values():
        if object.errors:
            if verbose:
                print(object.format())
                continue
            for loc, errs in object.errors.items():
                for err in errs:
                    print(
                        format.format(
                            file=str(loc.path),
                            line=loc.range.start.line + 1,
                            column=loc.range.start.character + 1,
                            severity=type(err).__name__,
                            message=str(err)))

@command(
    transport_kind=Arg('--transport-kind', '-t', choices=['ipc', 'tcp'], help='Which transport protocol to use.'),
    host=Arg('--host', '-H', help='Hostname to bind server to.'),
    port=Arg('--port', '-p', help='Port number to bind server to.'),
    loglevel=Arg('--loglevel', '-l', choices=['error', 'warning', 'info', 'debug'], help='Logger loglevel.'),
    logfile=Arg('--logfile', '-L',  type=Path, help='Logfile name.'),
)
async def lsp(
    transport_kind: str = 'ipc',
    host: str = 'localhost',
    port: int = 0,
    loglevel: str = 'error',
    logfile: Path = Path('stexls.log')):
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
    logging.basicConfig(
        filename=logfile,
        level=getattr(logging, loglevel.upper()))
    if transport_kind == 'ipc':
        server, connection = await Server.open_ipc_connection()
    elif transport_kind == 'tcp':
        server, connection = await Server.open_connection(host=host, port=port)
    async with server:
        await connection


if __name__ == '__main__':
    cli = Cli(commands=[linter, lsp], description=__doc__, version=pkg_resources.require('stexls')[0].version)
    asyncio.run(cli.dispatch())