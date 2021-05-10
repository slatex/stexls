import logging
from pathlib import Path
from typing import List, Optional, Pattern

from tqdm import tqdm

from .linter import Linter
from ..util.workspace import Workspace
from ..vscode import DiagnosticSeverity


log = logging.getLogger(__name__)


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
