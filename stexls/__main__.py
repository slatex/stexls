''' This is the entrypoint for the language server.
The server can be used by using tcp sockets or
it can simply communicate with another process using
stdin and stdout. After the starver has started,  '''
import asyncio
import logging
import re
from argparse import REMAINDER, ArgumentParser
from pathlib import Path

import pkg_resources

from .linter.cli import linter
from .lsp.cli import lsp
from .vscode import DiagnosticSeverity

log = logging.getLogger(__name__)


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
        '--show-progress', '-p', action='store_true',
        help='Enables printing of a progress bar to stderr during update.')
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
        '--transport-kind', '-t', choices=['ipc', 'tcp'], help='Which transport protocol to use.')
    lsp_cmd.add_argument('--host', '-H', help='Hostname to bind server to.')
    lsp_cmd.add_argument('--port', '-p', help='Port number to bind server to.')
    lsp_cmd.add_argument(
        '--loglevel', '-l', choices=['error', 'warning', 'info', 'debug'], default='error', help='Logger loglevel.')
    lsp_cmd.add_argument(
        '--logfile', '-L',  type=Path, help='Logfile name.', default=Path('stexls.log')),

    test_model = subparsers.add_parser('test-model')

    args = vars(parser.parse_args())
    cmd = args.pop('command')
    if cmd == 'linter':
        asyncio.run(linter(**args))
    elif cmd == 'lsp':
        async def await_lsp():
            server, task = await lsp(**args)
            await task
        asyncio.run(await_lsp())
    elif cmd == 'test-model':
        from stexls.lsp.server import _get_default_trefier_model_path
        model_path = _get_default_trefier_model_path()
        from stexls.trefier.models.seq2seq import Seq2SeqModel
        model = Seq2SeqModel.load(model_path)
        model.model.summary()
    else:
        raise ValueError(args)
