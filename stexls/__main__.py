''' This is the entrypoint for the language server.
The server can be used by using tcp sockets or
it can simply communicate with another process using
stdin and stdout. After the starver has started,  '''
from typing import Pattern
import logging
import asyncio
import re
import pkg_resources
from tqdm import tqdm
from pathlib import Path

from stexls.util.cli import Cli, command, Arg
from stexls.vscode import *
from stexls.util.workspace import Workspace
from stexls.linter import Linter
from stexls.lsp import Server

log = logging.getLogger(__name__)


@command(
    files=Arg(type=Path, nargs='+', help='List of files for which to generate diagnostics.'),
    root=Arg(required=True, type=Path, help="Root directory. Required to resolve imports."),
    diagnosticlevel=Arg('--diagnosticlevel', '-d', choices=('error', 'warning', 'info'), help='Only diagnostics for the specified level and above are printed.'),
    include=Arg('--include', '-I', nargs='+', type=re.compile, help='List of regex patterns. Only files that match ANY of these patterns will be included.'),
    ignore=Arg('--ignore', '-i', nargs='+', type=re.compile, help='List of regex pattern. All files that match ANY of these patterns will be excluded.'),
    verbose=Arg('--verbose', '-v', action='store_true', help='If enabled, instead of only printing errors, this will print all infos about each input file.'),
    show_progress=Arg('--show-progress', '-p', action='store_true', help='Enables printing of a progress bar to stderr during update.'),
    num_jobs=Arg('--num-jobs', '-j', type=int, help='Specifies the number of processes to use for compiling.'),
    format=Arg('--format', '-F', help='Formatter for the diagnostics.'),
    tagfile=Arg('--tagfile', '-t', const='tags', action='store', nargs='?', help='Optional name for a vim tagfile. If used without a value "tags" will be used. If not specified, no tagfile will be generated.'),
    loglevel=Arg('--loglevel', '-l', choices=['error', 'warning', 'info', 'debug'], help='Logger loglevel.'),
    logfile=Arg('--logfile', '-L', type=Path, help='Optional path to a logfile.')
)
async def linter(
    files: List[Path],
    root: Path = '.',
    diagnosticlevel: str = 'info',
    include: List[Pattern] = None,
    ignore: List[Pattern] = None,
    show_progress: bool = False,
    verbose: bool = False,
    num_jobs: int = 1,
    format: str = '{file}:{line}:{column} {severity} - {message}',
    tagfile: str = None,
    loglevel: str = 'error',
    logfile: Path = Path('/tmp/stexls.log')):
    """ Run the language server in linter mode.

        In this mode only diagnostics and progress are printed to stdout.

    Parameters:
        root: Root of stex imports.
        files: List of input files. While dependencies are compiled, only these specified files will generate diagnostics.
        diagnosticlevel: Only diagnostics for the specified level and above are printed. Choices are "error", "warning" and "info".
        include: List of regex patterns. Only files that match ANY of these patterns will be included.
        ignore: List of regex pattern. All files that match ANY of these patterns will be excluded.
        show_progress: Enables a progress bar being printed to stderr.
        verbose: If enabled, instead of only printing errors, all infos about each input file will be printed.
        num_jobs: Number of processes to use for compilation.
        format: Format string of the diagnostics. Variables are 'file', 'line', 'column', 'severity' and 'message'
        tagfile: Optional name of the generated tagfile. If None, no tagfile will be generated.
        loglevel: Server loglevel. Choices are critical, error, warning, info and debug.
        logfile: File to which logs will be logged.

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
    def progressfn(it, title, files):
        log.debug('Progress "%s":%i', title, len(it))
        if show_progress:
            try:
                it = tqdm(it, total=len(it))
                if files is not None:
                    assert len(files) == len(it), 'Length of input iterator and provided file list do not match.'
            except:
                it = tqdm(it, total=None if files is None else len(files))
            it.set_description(title)
        return it

    workspace = Workspace(root)
    workspace.ignore = ignore
    workspace.include = include
    linter = Linter(
        workspace=workspace,
        outdir=outdir,
        enable_global_validation=False,
        num_jobs=num_jobs,
        on_progress_fun=progressfn)

    if tagfile:
        log.debug('Creating tagfile at "%s"', root / tagfile)
        # TODO: Tagfile

    for file in progressfn(files, 'Linting', files):
        ln = linter.lint(file)
        log.debug('Dumping %s diagnostics in .', len(ln.object.errors), ln.object.file)
        if verbose:
            print(ln.object.format())
        else:
            ln.format_messages(format=format, diagnosticlevel=diagnosticlevel)

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
    logfile: Path = Path('/tmp/stexls.log')):
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
    async with server:
        await connection


if __name__ == '__main__':
    try:
        version = pkg_resources.require('stexls')[0].version
    except:
        version = 'undefined'
    cli = Cli(commands=[linter, lsp], description=__doc__, version=version)
    asyncio.run(cli.dispatch())
