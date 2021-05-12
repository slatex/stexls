import logging
from asyncio import Task
from pathlib import Path
from typing import Any, Dict, Literal, Tuple

from .server import Server


def _get_default_trefier_model_path() -> Path:
    return Path(__file__).parent.parent / 'seq2seq.model'


async def lsp(
        num_jobs: int = 1,
        update_delay_seconds: float = 2.0,
        enable_global_validation: bool = False,
        lint_workspace_on_startup: bool = False,
        enable_linting_of_related_files: bool = False,
        enable_trefier: bool = False,
        transport_kind: Literal['ipc', 'tcp'] = 'ipc',
        host: str = 'localhost',
        port: int = 0,
        loglevel: str = 'error',
        logfile: Path = Path('stexls.log')) -> Tuple[Server, Task]:
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
        assert _get_default_trefier_model_path().is_file()
        shared_args['path_to_trefier_model'] = _get_default_trefier_model_path()
    if transport_kind == 'ipc':
        server, connection = await Server.open_ipc_connection(**shared_args)
    elif transport_kind == 'tcp':
        server, connection = await Server.open_connection(host=host, port=port, **shared_args)
    assert isinstance(server, Server)
    return server, connection
