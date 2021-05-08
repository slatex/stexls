''' This is the entrypoint for the language server.
The server can be used by using tcp sockets or
it can simply communicate with another process using
stdin and stdout. After the starver has started,  '''
import asyncio
import logging
import re
from argparse import ArgumentParser, REMAINDER
from pathlib import Path
from typing import Any, Dict, List, Optional, Pattern

import pkg_resources
from tqdm import tqdm

from .linter.linter import Linter
from .lsp.server import Server
from .trefier.models.seq2seq import Seq2SeqModel
from .util.workspace import Workspace
from .vscode import DiagnosticSeverity

log = logging.getLogger(__name__)


def _get_default_trefier_model_path() -> Path:
    return Path(__file__).parent / 'seq2seq.model'


async def linter(
        files: List[Path],
        root: Optional[Path],
        diagnosticlevel: DiagnosticSeverity,
        include: List[Pattern],
        ignore: List[Pattern],
        enable_trefier: bool,
        show_progress: bool,
        num_jobs: int,
        format: str,
        tagfile: Optional[str],
        loglevel: str,
        logfile: Path,
        verbose: bool):
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
    root = (root or Path.cwd()).expanduser().resolve().absolute()
    stexls_home = root / '.stexls'
    stexls_home.mkdir(exist_ok=True)
    if not logfile.expanduser().is_absolute():
        logfile = stexls_home / logfile
    logging.basicConfig(
        filename=logfile,
        level=getattr(logging, loglevel.upper()))
    log.debug('Setting root to "%s"', root)
    outdir = stexls_home / 'objects'
    outdir.mkdir(exist_ok=True)
    log.debug('Compiler outdir at "%s"', outdir)

    def progressfn(it, title, files):
        log.debug('Progress "%s":%i', title, len(it))
        if show_progress:
            try:
                it = tqdm(it, total=len(it))
                if files is not None:
                    assert len(files) == len(
                        it), 'Length of input iterator and provided file list do not match.'
            except Exception:
                it = tqdm(it, total=None if files is None else len(files))
            it.set_description(title)
        return it

    workspace = Workspace(root)
    workspace.ignore = ignore
    workspace.include = include

    if not files:
        files = list(workspace.files)
        log.info('No files provided: Linting all %i files in workspace', len(files))

    linter = Linter(
        workspace=workspace,
        outdir=outdir,
        enable_global_validation=False,
        num_jobs=num_jobs)

    trefier_model: Optional[Seq2SeqModel] = None
    try:
        if enable_trefier:
            trefier_model_path = _get_default_trefier_model_path()
            log.debug('Loading trefier from "%s"', trefier_model_path)
            from stexls.trefier.models.seq2seq import Seq2SeqModel

            # TODO: Use the trefier model
            trefier_model = Seq2SeqModel.load(trefier_model_path)
            print(trefier_model)
            del trefier_model
    except Exception:
        log.exception('Failed to load trefier model')

    if tagfile:
        log.debug('Creating tagfile at "%s"', root / tagfile)
        # TODO: Tagfile

    buffer = []
    for file in progressfn(files, 'Linting', files):
        try:
            ln = linter.lint(file.expanduser().resolve().absolute())
        except Exception as err:
            log.exception('Failed to lint file: %s', file)
            buffer.append(f'{file} Failed to lint file: {err} ({type(err)})')
            continue
        log.debug('Dumping %s diagnostics in .', len(ln.diagnostics))
        if verbose:
            verbose_format = ln.object.format()
            buffer.append(verbose_format)
        else:
            messages = ln.format_messages(
                format_string=format, diagnosticlevel=diagnosticlevel)
            buffer.extend(messages)

    print('\n'.join(buffer))


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
        logfile: Path = Path('stexls.log')):
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
    shared_args: Dict[str, Any] = {
        'num_jobs': num_jobs,
        'update_delay_seconds': update_delay_seconds,
        'enable_global_validation': enable_global_validation,
        'lint_workspace_on_startup': lint_workspace_on_startup,
        'enable_linting_of_related_files_on_change': enable_linting_of_related_files,
    }
    if enable_trefier:
        shared_args['path_to_trefier_model'] = _get_default_trefier_model_path()
    if transport_kind == 'ipc':
        _server, connection = await Server.open_ipc_connection(**shared_args)
        await connection
    elif transport_kind == 'tcp':
        _server, connection = await Server.open_connection(host=host, port=port, **shared_args)
        await connection


if __name__ == '__main__':
    parser = ArgumentParser()
    try:
        version = pkg_resources.require('stexls')[0].version
    except Exception:
        version = 'undefined'
    parser.add_argument('--version', '-V', action='version', version=version)
    subparsers = parser.add_subparsers(dest='command', required=True)
    linter_cmd = subparsers.add_parser('linter')
    linter_cmd.add_argument(
        'files', type=Path, nargs=REMAINDER, help='List of files for which to generate diagnostics.')
    linter_cmd.add_argument(
        '--root', type=Path, help="Root directory. Required to resolve imports.")
    linter_cmd.add_argument(
        '--diagnosticlevel', '-d', type=DiagnosticSeverity.from_string,
        help='Only diagnostics for the specified level and above are printed.',
        default=DiagnosticSeverity.Hint)
    linter_cmd.add_argument(
        '--include', '-I', nargs='+', type=lambda x: re.compile(x),
        help='List of regex patterns. Only files that match ANY of these patterns will be included.',
        default=[re.compile(r'.*\.tex')])
    linter_cmd.add_argument(
        '--ignore', '-i', nargs='+', type=lambda x: re.compile(x),
        help='List of regex pattern. All files that match ANY of these patterns will be excluded.')
    linter_cmd.add_argument(
        '--enable-trefier', action='store_true',
        help="Enables machine learning trefier tagging.")
    linter_cmd.add_argument(
        '--show-progress', '-p', action='store_true',
        help='Enables printing of a progress bar to stderr during update.')
    linter_cmd.add_argument(
        '--num-jobs', '-j', type=int, default=1,
        help='Specifies the number of processes to use for compiling.')
    linter_cmd.add_argument(
        '--format', '-F', help='Formatter for the diagnostics.',
        default='{relative_file}:{line}:{column} {severity} - {message} ({code})')
    linter_cmd.add_argument(
        '--tagfile', '-t', const='tags', action='store', nargs='?',
        help='Optional name for a vim tagfile. If used without a value "tags" will be used. If not specified, no tagfile will be generated.')
    linter_cmd.add_argument(
        '--loglevel', '-l', choices=['error', 'warning', 'info', 'debug'], default='error', help='Logger loglevel.')
    linter_cmd.add_argument(
        '--logfile', '-L', type=Path, help='Path to a logfile.', default=Path('stexls.log'))
    linter_cmd.add_argument(
        '--verbose', '-v', action='store_true',
        help='If enabled, instead of only printing errors, this will print all infos about each input file.')

    lsp_cmd = subparsers.add_parser('lsp')
    lsp_cmd.add_argument(
        '--num-jobs', '-j', type=int, default=1,
        help="Number of processes used for multiprocessing.")
    lsp_cmd.add_argument(
        '--update-delay-seconds', '--update-delay', '--delay', type=float, help='Delay of the linter in seconds after a change is made.')
    lsp_cmd.add_argument(
        '--enable-global-validation', '-g', action='store_true',
        help=(
            "This will make the server compile every file in the workspace on startup,"
            " enabling global validation and diagnostics."
        ))
    lsp_cmd.add_argument(
        '--lint-workspace-on-startup', action='store_true',
        help="Create diagnostics for every file in the workspace on startup.")
    lsp_cmd.add_argument(
        '--enable-trefier', action='store_true', help="Enables machine learning trefier tagging.")
    lsp_cmd.add_argument(
        '--enable-linting-of-related-files', action='store_true',
        help="The server will lint every file that reference a changed file, directly or transitively.")
    lsp_cmd.add_argument(
        '--transport-kind', '-t', choices=['ipc', 'tcp'], help='Which transport protocol to use.')
    lsp_cmd.add_argument('--host', '-H', help='Hostname to bind server to.')
    lsp_cmd.add_argument('--port', '-p', help='Port number to bind server to.')
    lsp_cmd.add_argument(
        '--loglevel', '-l', choices=['error', 'warning', 'info', 'debug'], default='error', help='Logger loglevel.')
    lsp_cmd.add_argument(
        '--logfile', '-L',  type=Path, help='Logfile name.', default=Path('stexls.log')),

    args = vars(parser.parse_args())
    cmd = args.pop('command')
    if cmd == 'linter':
        asyncio.run(linter(**args))
    elif cmd == 'lsp':
        asyncio.run(lsp(**args))
    else:
        raise ValueError(args)
