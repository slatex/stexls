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


def _get_default_trefier_model_path() -> Path:
    return Path(__file__).parent / 'seq2seq.model'

@command(
    files=Arg(type=Path, nargs='+', help='List of files for which to generate diagnostics.'),
    root=Arg(required=True, type=Path, help="Root directory. Required to resolve imports."),
    diagnosticlevel=Arg('--diagnosticlevel', '-d', type=DiagnosticSeverity.from_string, help='Only diagnostics for the specified level and above are printed.'),
    include=Arg('--include', '-I', nargs='+', type=re.compile, help='List of regex patterns. Only files that match ANY of these patterns will be included.'),
    ignore=Arg('--ignore', '-i', nargs='+', type=re.compile, help='List of regex pattern. All files that match ANY of these patterns will be excluded.'),
    enable_trefier=Arg('--enable_trefier', '--enable-trefier', action='store_true', help="Enables machine learning trefier tagging."),
    show_progress=Arg('--show-progress', '-p', action='store_true', help='Enables printing of a progress bar to stderr during update.'),
    num_jobs=Arg('--num-jobs', '-j', type=int, help='Specifies the number of processes to use for compiling.'),
    format=Arg('--format', '-F', help='Formatter for the diagnostics.'),
    tagfile=Arg('--tagfile', '-t', const='tags', action='store', nargs='?', help='Optional name for a vim tagfile. If used without a value "tags" will be used. If not specified, no tagfile will be generated.'),
    loglevel=Arg('--loglevel', '-l', choices=['error', 'warning', 'info', 'debug'], help='Logger loglevel.'),
    logfile=Arg('--logfile', '-L', type=Path, help='Optional path to a logfile.'),
    verbose=Arg('--verbose', '-v', action='store_true', help='If enabled, instead of only printing errors, this will print all infos about each input file.')
)
async def linter(
    files: List[Path],
    root: Path = '.',
    diagnosticlevel: DiagnosticSeverity = DiagnosticSeverity.Information,
    include: List[Pattern] = None,
    ignore: List[Pattern] = None,
    enable_trefier: bool = False,
    show_progress: bool = False,
    num_jobs: int = 1,
    format: str = '{relative_file}:{line}:{column} {severity} - {message} ({code})',
    tagfile: str = None,
    loglevel: str = 'error',
    logfile: Path = Path('/tmp/stexls.log'),
    verbose: bool = False):
    """ Run the language server in linter mode.

        In this mode only diagnostics and progress are printed to stdout.

    Parameters:
        root: Root of stex imports.
        files: List of input files. While dependencies are compiled, only these specified files will generate diagnostics.
        diagnosticlevel: Only diagnostics for the specified level and above are printed. (Error: 1, Warning: 2, Info: 3, Hint: 4)
        include: List of regex patterns. Only files that match ANY of these patterns will be included.
        ignore: List of regex pattern. All files that match ANY of these patterns will be excluded.
        enable_trefier: Enables machine learning trefier tagging.
        show_progress: Enables a progress bar being printed to stderr.
        verbose: If enabled, instead of only printing errors, all infos about each input file will be printed.
        num_jobs: Number of processes to use for compilation.
        format: Format string of the diagnostics. Variables are file, relative_file, line, column, severity, message and code.
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
        num_jobs=num_jobs)

    trefier_model = None
    try:
        if enable_trefier:
            trefier_model_path = _get_default_trefier_model_path()
            log.debug('Loading trefier from "%s"', trefier_model_path)
            trefier_model = Seq2SeqModel.load(trefier_model_path)
            # TODO: Use the trefier model
    except:
        log.exception('Failed to load trefier model')

    if tagfile:
        log.debug('Creating tagfile at "%s"', root / tagfile)
        # TODO: Tagfile

    buffer = []
    for file in progressfn(files, 'Linting', files):
        try:
            ln = linter.lint(file.absolute())
        except Exception as err:
            log.exception('Failed to lint file: %s', file)
            buffer.append(f'{file} Failed to lint file: {err} ({type(err)})')
            continue
        log.debug('Dumping %s diagnostics in .', len(ln.diagnostics))
        if verbose:
            verbose_format = ln.object.format()
            buffer.append(verbose_format)
        else:
            messages = ln.format_messages(format_string=format, diagnosticlevel=diagnosticlevel)
            buffer.extend(messages)

    print('\n'.join(buffer))

@command(
    num_jobs=Arg('--num_jobs', '-j', type=int, help="Number of processes used for multiprocessing."),
    update_delay_seconds=Arg('--update_delay_seconds', '--update-delay', '--delay', type=float, help='Delay of the linter in seconds after a change is made.'),
    enable_global_validation=Arg('--enable_global_validation', '--enable-global-validation', '-g', action='store_true', help="This will make the server compile every file in the workspace on startup, enabling global validation and diagnostics."),
    lint_workspace_on_startup=Arg('--lint_workspace_on_startup', '--lint-workspace-on-startup', action='store_true', help="Create diagnostics for every file in the workspace on startup."),
    enable_trefier=Arg('--enable_trefier', '--enable-trefier', action='store_true', help="Enables machine learning trefier tagging."),
    enable_linting_of_related_files=Arg('--enable_linting_of_related_files', '--enable-linting-of-related-files', action='store_true', help="The server will lint every file that reference a changed file, directly or transitively."),
    transport_kind=Arg('--transport-kind', '-t', choices=['ipc', 'tcp'], help='Which transport protocol to use.'),
    host=Arg('--host', '-H', help='Hostname to bind server to.'),
    port=Arg('--port', '-p', help='Port number to bind server to.'),
    loglevel=Arg('--loglevel', '-l', choices=['error', 'warning', 'info', 'debug'], help='Logger loglevel.'),
    logfile=Arg('--logfile', '-L',  type=Path, help='Logfile name.'),
)
async def lsp(
    num_jobs: int = 1,
    update_delay_seconds: float = 2.0,
    enable_global_validation: bool = False,
    lint_workspace_on_startup: bool = False,
    enable_linting_of_related_files: bool = False,
    enable_trefier: bool = False,
    transport_kind: str = 'ipc',
    host: str = 'localhost',
    port: int = 0,
    loglevel: str = 'error',
    logfile: Path = Path('/tmp/stexls.log')):
    """ Starts the language server in either ipc or tcp mode.

    Parameters:
        num_jobs: The number of processes used for multiprocessing.
        update_delay_seconds: The number of seconds the server is waiting for more input before proceeding to lint the changed files.
        enable_global_validation: Enables global validation of references.
        lint_workspace_on_startup: Create diagnostics for every file in the workspace on startup.
        enable_trefier: Enables machine learning trefier tagging.
        enable_linting_of_related_files: The server will lint every file that reference a changed file, directly or transitively.
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
    server, connection = None, None
    shared_args = {
        'num_jobs': num_jobs,
        'update_delay_seconds': update_delay_seconds,
        'enable_global_validation': enable_global_validation,
        'lint_workspace_on_startup': lint_workspace_on_startup,
        'enable_linting_of_related_files_on_change': enable_linting_of_related_files,
    }
    if enable_trefier:
        shared_args['path_to_trefier_model'] = _get_default_trefier_model_path()
    if transport_kind == 'ipc':
        server, connection = await Server.open_ipc_connection(**shared_args)
    elif transport_kind == 'tcp':
        server, connection = await Server.open_connection(host=host, port=port, **shared_args)
    async with server:
        await connection


if __name__ == '__main__':
    try:
        version = pkg_resources.require('stexls')[0].version
    except:
        version = 'undefined'
    cli = Cli(commands=[linter, lsp], description=__doc__, version=version)
    asyncio.run(cli.dispatch())
