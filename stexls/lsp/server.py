import asyncio
import datetime
import logging
import sys
import time
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Protocol, Set, Union
from urllib.parse import urlparse

import pkg_resources
from stexls.util.unwrap import unwrap

from .. import vscode
from ..jsonrpc.dispatcher import Dispatcher
from ..jsonrpc.exceptions import InvalidRequestException
from ..jsonrpc.hooks import alias, method, notification, request
from ..linter.linter import Linter
from ..trefier.models.seq2seq import Seq2SeqModel
from ..util.workspace import Workspace
from .completions import CompletionEngine
from .exceptions import ServerNotInitializedException
from .state import ServerState
from .workspace_symbols import WorkspaceSymbols

log = logging.getLogger(__name__)


class Cancelable(Protocol):
    def cancel(self) -> bool:
        ...


def _get_default_trefier_model_path() -> Path:
    return Path.home() / '.trefier' / 'seq2seq.model'
    return Path(__file__).parent.parent / 'seq2seq.model'


@dataclass
class InitializationOptions:
    compile_workspace_on_startup_file_limit: int = 0
    enable_trefier: Literal['disabled', 'enabled', 'full'] = 'disabled'
    enable_linting_of_related_files: bool = False
    num_jobs: int = 1
    delay: float = 1
    trefier_download_link: str = ''
    trefier_file_size_limit_kb: int = 50
    linter_file_size_limit_kb: int = 100

    @staticmethod
    def from_json(obj: dict):
        return InitializationOptions(
            compile_workspace_on_startup_file_limit=int(
                obj["compileWorkspaceOnStartupFileLimit"]),
            enable_trefier=obj["enableTrefier"],
            enable_linting_of_related_files=bool(
                obj['enableLintingOfRelatedFiles']),
            num_jobs=int(obj['numJobs']),
            delay=float(obj['delay']),
            trefier_download_link=str(obj.get('trefierDownloadLink', '')),
            trefier_file_size_limit_kb=int(
                obj.get('trefierFileSizeLimitKB', 50)),
            linter_file_size_limit_kb=int(
                obj.get('linterFileSizeLimitKB', 100)),
        )


class Server(Dispatcher):
    def __init__(self, connection):
        """ Creates a server dispatcher.

        Parameters:
            connection: Inherited from Dispatcher. This argument is automatically provided by the class' initialization method.
        """
        super().__init__(connection=connection)
        # Version
        try:
            self.version: Optional[str] = str(
                pkg_resources.require('stexls')[0].version)
        except Exception:
            self.version = None
        # Initialization options from `initialize` request
        self.initialization_options = InitializationOptions()
        # State the serer is in
        self.state = ServerState.UNINITIALIZED
        # If this is false, then the server must not send progress information
        self.work_done_progress_capability: bool = False
        # Path to the root directory
        self.root_directory: Optional[Path] = None
        # trefier model loaded from path_to_trefier_model
        self.trefier_model: Optional[Seq2SeqModel] = None
        # Workspace instance, used to keep track of file buffers
        self.workspace: Optional[Workspace] = None
        # Linter instance, used to create diagnostics
        self.linter: Optional[Linter] = None
        # Completion engine used to encapsulate the complex process of creating completion suggestions
        self.completion_engine: Optional[CompletionEngine] = None
        # Manager for work done progress bars
        self.cancellable_work_done_progresses: Dict[object, Cancelable] = {}
        # Accumulator for symbols in workspace, used for suggestions and fast search of missing modules etc
        # TODO: Currently still unused.
        self.workspace_symbols = WorkspaceSymbols()
        # Scheduler for publishing diagnostics
        self.scheduler: Optional[LintingScheduler] = None

    @method
    @alias('$/progress')
    def receive_progress(
            self,
            token: Union[int, str],
            value: Union[vscode.WorkDoneProgressBegin, vscode.WorkDoneProgressReport, vscode.WorkDoneProgressEnd]):
        self.protect_from_uninit_and_shutdown()
        log.info('Progress %s received: %s', token, value)

    @notification
    @alias('$/progress')
    def send_progress(
            self,
            token: Union[int, str],
            value: Union[vscode.WorkDoneProgressBegin, vscode.WorkDoneProgressReport, vscode.WorkDoneProgressEnd]):
        pass

    @method
    async def initialize(
        self,
        capabilities: vscode.ClientCapabilities,
        workspaceFolders: Optional[List[vscode.WorkspaceFolder]] = None,
        processId: Optional[int] = None,
        clientInfo: Optional[dict] = None,
        locale: Optional[str] = None,
        rootPath: Optional[str] = None,
        rootUri: Optional[vscode.DocumentUri] = None,
        workDoneProgress: Union[
            int, str, vscode.Undefined] = vscode.undefined,
        initializationOptions: InitializationOptions = None,
        **kwargs,
    ):
        ''' Initializes the serverside.
        This method is called by the client that starts the server.
        The server may only respond to other requests after this method successfully returns.

        Until the server has responded to the initialize request with an InitializeResult,
        the client must not send any additional requests or notifications to the server.
        In addition the server is not allowed to send any requests or notifications
        to the client until it has responded with an InitializeResult,
        with the exception that during the initialize request the server is allowed to send the notifications window/showMessage,
        window/logMessage and telemetry/event as well as the window/showMessageRequest request to the client.
        In case the client sets up a progress token in the initialize params (e.g. property workDoneToken)
        the server is also allowed to use that token (and only that token)
        using the $/progress notification sent from the server to the client.
        '''
        if self.state != ServerState.UNINITIALIZED:
            raise ValueError('Server not uninitialized.')
        if self.state == ServerState.SHUTDOWN:
            raise InvalidRequestException('The server has shut down')
        log.info('stexls version: %s', self.version)
        self.initialization_options = unwrap(initializationOptions)
        log.info('Initialization options: %s',
                 str(self.initialization_options))

        # Work done progress may only be sent if the capability is set
        self.work_done_progress_capability = capabilities.window.get(
            'workDoneProgress', False)
        log.info('Work done progress capability: %s',
                 self.work_done_progress_capability)

        if isinstance(rootUri, vscode.DocumentUri):
            self.root_directory = Path(urlparse(rootUri).path)
        elif isinstance(rootPath, str):
            # rootPath is deprecated and must only be used if `rootUri` is not defined
            self.root_directory = Path(rootPath)
        else:
            raise RuntimeError('No root path in initialize.')
        log.info('root at: %s', self.root_directory)
        outdir = self.root_directory / '.stexls' / 'objects'
        self.workspace = Workspace(
            self.root_directory, ignorefile=Path('.stexlsignore'))
        if self.initialization_options.enable_trefier != 'disabled':
            await self.load_trefier_model()
        self.linter = Linter(
            workspace=self.workspace,
            outdir=outdir,
            trefier_file_size_limit_kb=(
                self.initialization_options.trefier_file_size_limit_kb),
            linter_file_size_limit_kb=(
                self.initialization_options.linter_file_size_limit_kb))
        if self.version is not None:
            self.linter.compiler.check_version(self.version)
        self.completion_engine = CompletionEngine(self.linter.linker)
        self.scheduler = LintingScheduler(
            server=self,
            delay=self.initialization_options.delay,
            linter=self.linter,
            workspace=self.workspace,
            trefier=self.trefier_model,
            enable_trefier=self.initialization_options.enable_trefier)
        self.state = ServerState.INITIALIZED
        return {
            'capabilities': {
                'textDocumentSync': {
                    'openClose': True,
                    'change': 1,  # TODO: full=1, incremental=2
                    'save': True,
                },
                'completionProvider': {
                    'triggerCharacters': ['?', '[', '{', ',', '='],
                    'allCommitCharacters': [']', '}', ','],
                },
                'definitionProvider': True,
                'referencesProvider': True,
                'workspace': {
                    'workspaceFolders': {
                        'supported': True,
                        'changeNotifications': True
                    }
                }
            },
            'serverInfo': {
                'name': 'stexls',
                'version': self.version
            }
        }

    async def load_trefier_model(self):
        """ Download and loads the trefier model. """
        model_path = _get_default_trefier_model_path()
        log.info('Loading trefier model from: %s', model_path)
        try:
            from stexls.trefier.models.seq2seq import Seq2SeqModel
            if not model_path.is_file():
                model_url = self.initialization_options.trefier_download_link
                if not model_url:
                    log.warning('Trefier download link is not set.')
                    return
                from ..util.download import maybe_download_and_extract
                self.show_message(type=vscode.MessageType.Info,
                                  message=f'Downloading trefier model to {str(model_path)!r}.')
                loop = asyncio.get_running_loop()
                log.info('Downloading trefier model from "%s" to "%s"',
                         model_url, str(model_path.parent))
                download_path = await loop.run_in_executor(
                    None, lambda: maybe_download_and_extract(model_url, model_path.parent.as_posix(), silent=True))
                assert isinstance(download_path, Path)
                log.info('Finished downloading trefier model... %s',
                         download_path.is_file())
                model_path = download_path.rename(
                    _get_default_trefier_model_path())
            self.trefier_model: Seq2SeqModel = Seq2SeqModel.load(model_path)
        except ImportError:
            log.exception('Failed to import seq2seq model dependencies.')
            self.show_message(
                type=vscode.MessageType.Error, message=(
                    'Trefier disabled: PIP dependencies required by the trefier were not met. Information has been written to the logfile.'))
        except zipfile.BadZipFile:
            log.exception(
                'Bad Zip file error: Probably because "git lfs" is not installed.')
            self.show_message(
                type=vscode.MessageType.Error, message=(
                    'Trefier disabled: Make sure you have git lfs installed.'
                    ' Then UNINSTALL and INSTALL stexls again.'))
        except Exception as err:
            log.exception('Failed to load seq2seq model')
            self.show_message(
                type=vscode.MessageType.Error, message=f'{type(err).__name__}: {err}')

    @method
    async def initialized(self):
        ' Event called by the client after it finished initialization. '
        if self.state == ServerState.UNINITIALIZED:
            raise ServerNotInitializedException()
        if self.state != ServerState.INITIALIZED:
            raise ValueError(
                '`initialized` method can only be called once directly following `initialize`.')
        try:
            num_files = len(list(self.linter.workspace.files))
            log.info(
                'Compiling workspace with %i files (limit %i) in order to buffer objects for global validation.',
                num_files, self.initialization_options.compile_workspace_on_startup_file_limit)
            limit_is = self.initialization_options.compile_workspace_on_startup_file_limit
            if 0 < limit_is < num_files:
                self.show_message(
                    type=vscode.MessageType.Info,
                    message=(
                        f'Your workspace has more .tex files ({num_files}), '
                        f'than your limit ({limit_is}). You can increase it '
                        'or disable it in settings UI under "stexls: Compile Workspace On Startup File Limit"')
                )
            async with ProgressBar(
                    server=self,
                    title=f'Compiling {num_files} files',
                    cancellable=False,
                    enabled=self.work_done_progress_capability) as progress_bar:
                await progress_bar.begin()
                compiled_files = self.linter.compile_workspace(
                    limit_is, self.initialization_options.num_jobs)
                # Sort the file in ascending order -> Add the newest file list -> Will be the file first linted.
                sorted_compiled_files = sorted(
                    compiled_files, key=self.workspace.get_time_modified)
                # Schedule all compiled files for linting
                unwrap(self.scheduler).schedule(
                    *sorted_compiled_files, prio='low')
        except Exception:
            log.exception('An error occured while compiling workspace')
        self.state = ServerState.READY
        log.info('Initialized')

    @method
    def shutdown(self):
        log.info('Shutting down server...')
        # TODO: Do stuff on shutdown?

    @method
    def exit(self):
        log.info('exit')
        sys.exit()

    @notification
    @alias('window/showMessage')
    def show_message(self, type: vscode.MessageType, message: str):
        pass

    @request
    @alias('window/showMessageRequest')
    def show_message_request(self, type: vscode.MessageType, message: str, actions: List[vscode.MessageActionItem]):
        pass

    @request
    @alias('window/logMessage')
    def log_message(self, type: vscode.MessageType, message: str):
        pass

    @request
    @alias('window/workDoneProgress/create')
    def window_work_done_progress_create(self, token: Union[int, str]):
        pass

    @method
    @alias('window/workDoneProgress/cancel')
    def window_work_done_progress_cancel(self, token: Union[int, str]):
        log.info('Cancelling work done progress token: %s', token)
        cancelable = self.cancellable_work_done_progresses.get(token)
        if cancelable is None:
            log.error('Unknown progress token: %s', token)
        elif not cancelable.cancel():
            log.warning('Token already cancelled: %s', token)

    @method
    @alias('textDocument/definition')
    async def definition(
            self,
            textDocument: vscode.TextDocumentIdentifier,
            position: vscode.Position,
            workDoneToken: Union[int, str,
                                 vscode.Undefined] = vscode.undefined,
            **params):
        self.protect_from_uninit_and_shutdown()
        log.debug('definitions(%s, %s)', textDocument.path, position.format())
        definitions = unwrap(self.linter).definitions(
            textDocument.path, position)
        log.debug('Found %i definitions: %s', len(definitions), definitions)
        return definitions

    @method
    @alias('textDocument/references')
    async def references(
            self,
            textDocument: vscode.TextDocumentIdentifier,
            position: vscode.Position,
            context: Any = vscode.undefined,
            **params):
        self.protect_from_uninit_and_shutdown()
        log.debug('references(%s, %s)', textDocument.path, position.format())
        references = unwrap(self.linter).references(
            textDocument.path, position)
        log.debug('Found %i references: %s', len(references), references)
        return references

    @method
    @alias('textDocument/completion')
    async def completion(
            self,
            textDocument: vscode.TextDocumentIdentifier,
            position: vscode.Position,
            context: Union[vscode.CompletionContext,
                           vscode.Undefined] = vscode.undefined,
            **kwargs):
        self.protect_from_uninit_and_shutdown()
        log.debug('completion(%s, %s, context=%s)',
                  textDocument.path, position.format(), context)
        return []

    @notification
    @alias('textDocument/publishDiagnostics')
    def publish_diagnostics(self, uri: vscode.DocumentUri, diagnostics: List[vscode.Diagnostic]):
        pass

    @method
    @alias('textDocument/didOpen')
    async def text_document_did_open(self, textDocument: vscode.TextDocumentItem):
        self.protect_from_uninit_and_shutdown()
        did_open = unwrap(self.workspace).open_file(
            textDocument.path, textDocument.version, textDocument.text)
        log.debug('didOpen(%s) -> %s', textDocument, did_open)
        unwrap(self.scheduler).schedule(textDocument.path, prio='high')

    @method
    @alias('textDocument/didChange')
    async def text_document_did_change(
            self,
            textDocument: vscode.VersionedTextDocumentIdentifier,
            contentChanges: List[vscode.TextDocumentContentChangeEvent]):
        # NOTE: Because there is no handler for the annotation type "List": contentChanges is a list of dictionaries!
        self.protect_from_uninit_and_shutdown()
        log.debug('Buffering file "%s" with version %i',
                  textDocument.path, textDocument.version)
        if not self.workspace:
            return
        if self.workspace.is_open(textDocument.path):
            for item in contentChanges:
                status = self.workspace.update_file(
                    # TODO: `item` has to be properly deserialized !
                    # TODO: Implement recursive annotations module
                    textDocument.path, textDocument.version, item['text'])  # type: ignore
                if not status:
                    log.warning('Failed to patch file with: %s', item)
        else:
            log.warning(
                'didChange event for non-opened document: "%s"', textDocument.path)

    @method
    @alias('textDocument/didClose')
    async def text_document_did_close(self, textDocument: vscode.TextDocumentIdentifier):
        self.protect_from_uninit_and_shutdown()
        log.debug('Closing document: "%s"', textDocument.path)
        if not self.workspace:
            return
        status = self.workspace.close_file(textDocument.path)
        if not status:
            log.warning('Failed to close file: "%s"', textDocument.path)

    @method
    @alias('textDocument/didSave')
    async def text_document_did_save(
            self,
            textDocument: vscode.TextDocumentIdentifier,
            text: Union[str, vscode.Undefined] = vscode.undefined):
        self.protect_from_uninit_and_shutdown()
        if unwrap(self.workspace).is_open(textDocument.path):
            log.info('didSave: %s', textDocument.uri)
            if not unwrap(self.scheduler).schedule(textDocument.path, prio='high'):
                return
            if self.initialization_options.enable_linting_of_related_files:
                users = unwrap(self.linter).find_users_of_file(
                    textDocument.path)
                users_sorted = sorted(
                    users, key=unwrap(self.workspace).get_time_modified)
                for user in users_sorted:
                    unwrap(self.scheduler).schedule(
                        user, prio='low', starts_loop=False)
        else:
            log.warning('didSave event for untracked file: %s',
                        textDocument.uri)

    def protect_from_uninit_and_shutdown(self):
        """ Raises appropriate exceptions depending on server state.

        Should only be called by methods that are not `shutdown`, `exit`, `initialize` and `initialized`.

        Raises:
            ServerNotInitializedException: Method called without initializing first.
            InvalidRequestException: Method called after shutdown.
        """
        if self.state == ServerState.UNINITIALIZED:
            raise ServerNotInitializedException()
        if self.state == ServerState.SHUTDOWN:
            raise InvalidRequestException('The server has shut down')


class ProgressBar:
    """ Helper class that handles the creation and update of progressbars. """

    def __init__(self,
                 server: Server,
                 title: str = None,
                 cancellable: bool = False,
                 total: int = None,
                 begin_message: str = None,
                 end_message: str = None,
                 enabled: bool = False) -> None:
        """ Initializes a progressbar. It still must be created using the @create() async task.

        Parameters:
            server: The server instance, needed to communicate with the client.
            title: Title of the process.
            cancellable: Flag enabling the cancel button on the client side.
            total: Total number of times this progress bar will be updated. Used to create a progressbar with percentage information.
            end_message: Message sent when the progress finishes using an async with statement.
        """
        self._server = server
        self._title = title
        self._end_message = end_message
        self.token = str(uuid.uuid4())
        self._cancellable = cancellable
        self.total = total
        self._begin_message_sent: bool = False
        self.created: bool = False
        self.enabled = enabled
        self._on_finished_event: asyncio.Future = asyncio.Future()

    async def __aenter__(self):
        try:
            await self.create()
        except asyncio.CancelledError:
            log.warning('The progress was cancelled while initializing.')
        except Exception:
            log.exception('Client refused progress bar creation')
            raise
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        await self.end(self._end_message)
        if exc_type == asyncio.CancelledError:
            log.info('Progressbar cancelled by user input: %s', exc_value)
            return True
        if None not in (exc_type, exc_value, traceback):
            log.exception(
                'An exception occured while a progress bar was running')

    def cancel(self) -> bool:
        ' Cancels the underlying @on_finished_event future object. Returns true if cancelling was successful. '
        if not self._on_finished_event.done():
            self._on_finished_event.cancel()
            return True
        return False

    async def create(self):
        ''' Needs to be called before it can be used. Used to initialize the progress bar on the client side.

        If the client raises an error during this call, no further progress information may be sent to the client.
        '''
        if not self.enabled:
            return
        created = self._server.window_work_done_progress_create(
            token=self.token)
        try:
            await created
        except Exception as err:
            self._on_finished_event.set_exception(err)
            raise
        self.created = True

    async def begin(self, message: str = None):
        ' Sends a begin message with optional text. '
        if not self.enabled:
            return
        if self.created:
            if self._begin_message_sent:
                raise ValueError('ProgressBar begin() called more than once.')
            if self._on_finished_event.cancelled():
                # Raise if canceled
                await self._on_finished_event
            args: Dict[str, Any] = {}
            if self._title is not None:
                args['title'] = self._title
            if self.total is not None:
                args['percentage'] = 0
            if message is not None:
                args['message'] = message
            begin = vscode.WorkDoneProgressBegin(
                cancellable=self._cancellable, **args)
            self._server.send_progress(token=self.token, value=begin)
        self._begin_message_sent = True

    async def update(self, iteration_progress_count: int = None, message: str = None, cancellable: bool = None):
        if not self.enabled:
            return
        if not self.created:
            # raise ValueError(f'Progress "{self.token}" not created by client.')
            return  # Return if not created
        if not self._begin_message_sent:
            raise ValueError(
                'Begin message must be sent before using the progressbar.')
        if self._on_finished_event.cancelled():
            # Raise if canceled
            await self._on_finished_event
        args: Dict[str, Any] = {}
        if self.total is not None and iteration_progress_count is not None:
            args['percentage'] = int(
                100 * iteration_progress_count / self.total)
        if message is not None:
            args['message'] = message
        if cancellable is not None:
            args['cancellable'] = cancellable
        report = vscode.WorkDoneProgressReport(**args)
        self._server.send_progress(token=self.token, value=report)

    async def end(self, message: str):
        if not self.enabled:
            return
        if not self.created:
            # raise ValueError(f'Progress "{self.token}" not created by client.')
            return  # Return if not created
        end = vscode.WorkDoneProgressEnd(message=message)
        self._server.send_progress(token=self.token, value=end)
        if not self._on_finished_event.done():
            # Only set event if not canceled or already returned
            self._on_finished_event.set_result(True)


class LintingScheduler:
    def __init__(
        self,
        server: Server,
        delay: float,
        linter: Linter,
        workspace: Workspace,
        trefier: Optional[Seq2SeqModel],
        enable_trefier: Literal['disabled', 'enabled', 'full'],
    ) -> None:
        self.delay = delay
        self.server = server
        self.linter = linter
        self.workspace = workspace
        self.trefier = trefier
        self.enable_trefier = enable_trefier
        self.lint_queue_high: List[Path] = []
        self.lint_queue_low: List[Path] = []
        self.task: Optional[Cancelable] = None
        self.timeout: Optional[asyncio.TimerHandle] = None
        self.never_linted_files: Set[Path] = set()

    async def _handle_high_priority(self) -> bool:
        """ Lint a file from the high priority queue.

        Applies the trefier to high priority requests.

        Returns:
            bool: True if a high priority file was linted.
        """
        if not self.lint_queue_high:
            return False
        file = self.lint_queue_high.pop()
        log.debug('Linting high prio: %s', file)
        await self.lint(file, trefier=self.trefier)
        return True

    async def _handle_low_priority(self) -> bool:
        """ Lint a file from the low priority queue.

        Low priority files do not use the trefier by default.

        Returns:
            bool: True if a low priority file was linted.
        """
        if not self.lint_queue_low:
            return False
        file = self.lint_queue_low.pop()
        log.debug('Linting low prio: %s', file)
        trefier = None
        if self.enable_trefier == 'full':
            # Enable trefier, if "full" mode
            trefier = self.trefier
        await self.lint(file, trefier=trefier)
        return True

    async def _handle_unbuffered(self, files: List[Path]) -> bool:
        """ Search for a file that is not buffered by the linter and buffer it.

        Args:
            files (List[Path]): Files to consider.

        Returns:
            bool: True if a file was buffered. False otherwise.
        """
        unbuffered_files = filter(
            lambda file: file not in self.linter.unlinked_object_buffer,
            files)
        unbuffered_file = next(unbuffered_files, None)
        if not unbuffered_file:
            return False
        # If there is a file that is not buffered,
        # Compile it and buffer the result.
        log.debug('Lint unbuffered object: %s', unbuffered_file)
        await self.lint(unbuffered_file, None)
        return True

    async def loop(self):
        """ The main loop of the scheduler.

        The loop is automatically started and postponed until started
        by the `schedule` method.
        The same loop runs until all files have been linted.

        After all files have been linted the loop stops, but is restarted
        after a short delay after a new scheduling requests comes in.

        The loop will not start as long as new scheduling requests come in
        in order to prevent useless linting while the user is still editing a file.
        """
        log.info('Scheduler loop started.')
        try:
            begin = time.time()
            loop_time = time.time()
            averate_loop_time = 1
            loop_count = 0
            update_freq_sec = 5
            last_update_time = time.time()
            async with ProgressBar(self.server, 'Linting', enabled=self.server.work_done_progress_capability) as pbar:
                await pbar.begin(message=f'{len(self.lint_queue_high) + len(self.lint_queue_low)} files')

                while True:
                    loop_count += 1
                    items_left = len(self.lint_queue_high) + \
                        len(self.lint_queue_low)
                    tend = time.time()
                    time_elapsed = tend - begin
                    loop_time_elapsed = tend - loop_time
                    averate_loop_time = time_elapsed / loop_count
                    eta = datetime.timedelta(seconds=round(
                        items_left * averate_loop_time))
                    loop_time = time.time()
                    if time.time() - last_update_time > update_freq_sec:
                        await pbar.update(message=f'{items_left if items_left else "?"} files (eta {str(eta)})')
                        last_update_time = time.time()
                    log.debug('Scheduler loop time: %s (%s), eta %s',
                              loop_time_elapsed, time_elapsed, str(eta))
                    loop_time = time.time()
                    if await self._handle_high_priority():
                        # Continue the loop else the priorities would not have any effect
                        continue
                    elif await self._handle_low_priority():
                        # Continue, so that high priority is first again
                        continue
                    elif await self._handle_unbuffered(
                            list(sorted(
                                # Sort the workspace files, so that the most recently changed file is first to be linted.
                                self.workspace.files,
                                key=self.workspace.get_time_modified,
                                reverse=True))):
                        # Continue, so that high prio is first again
                        continue
                    # Reaching here means, that no file was in either queue,
                    # all files are buffered and no file need recompilation.
                    # We can exit the loop and clean up the task.
                    # (Cleanup is handled by the schedule timeout callback)
                    break
        except Exception:
            log.exception('Exception raised during scheduler loop.')
            raise
        finally:
            log.debug('Scheduler loop exited in %s seconds',
                      round(time.time() - begin))

    async def lint(self, file: Path, trefier: Optional[Seq2SeqModel]):
        # Running the linting in a thread makes everything take a bit longer than
        # running it directly, but without it, we would be unable to handle other requests
        # during linting.
        log.debug('Scheduler linting "%s" in using trefier (%s)',
                  str(file), trefier)
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, self.linter.lint, file, trefier)
        log.debug('Finished linting file "%s"', file)
        self.server.workspace_symbols.remove(file)
        self.server.workspace_symbols.add(result.object)
        self.server.publish_diagnostics(
            uri=file.as_uri(), diagnostics=result.diagnostics)

    def schedule(
        self,
        *files: Path,
        prio: Literal['high', 'low'],
        delay: Optional[float] = None,
        starts_loop: bool = True
    ) -> bool:
        """ Schedule a file for linting.

        Args:
            files (Path): Files that should be added to the schedule.
            prio (Literal['high', 'low']): Priority. The priority of a file can be increased,
                but multiple scheduling of low priorty files will be ignored.
            delay (Optional[float], optional): Override member delay. If None, then member value will be used. Defaults to None.

        Returns:
            bool: True if any file was added to a queue. False otherwise.
        """
        success = False
        # Filter out files that are ignored
        if self.workspace.ignorefile is not None:
            # Reload ignorefile
            try:
                self.workspace.ignorefile.load()
            except Exception:
                log.exception('Failed to parse ignorefile.')
            files = tuple(
                file for file in files if not self.workspace.ignorefile.match(file))
        if prio == 'high':
            for file in files:
                # Add to high priorty
                # promote if in any other queue already.
                if file in self.lint_queue_low:
                    self.lint_queue_low.remove(file)
                elif file in self.lint_queue_high:
                    # Promote to front of high queue if already queued
                    self.lint_queue_high.remove(file)
                else:
                    success = True
            self.lint_queue_high.extend(files)
        else:
            for file in files:
                # Add to low priority.
                # Promote to front of queue by removing it first if it already
                # was added to this queue
                if file in self.lint_queue_low:
                    self.lint_queue_low.remove(file)
                else:
                    success = True
            self.lint_queue_low.extend(files)
        log.debug('Scheduled %i files with %s priority: %s',
                  len(files), prio, files)
        # Check if there is a task that handles the queued items.
        # If not, we must start one.
        if success and starts_loop and self.task is None:
            log.debug('No scheduler loop running: Prepare timeout %s',
                      self.delay if delay is None else delay)
            if self.timeout is not None:
                # Cancel a planned task loop, because
                # files have been changed while still waiting
                # for another loop to start
                log.debug('Cancel current scheduler loop timeout.')
                self.timeout.cancel()

            def create_schedule_loop_task(expected_timeout_object: List[asyncio.TimerHandle]):
                " This function handles creation and cleanup of the timeout/task members. "
                log.debug(
                    'Create schedule loop task after timeout: %s', self.timeout)
                if any(
                        self.timeout is not to for to in expected_timeout_object):
                    log.critical(
                        'Failed to properly create scheduler loop task because the timeout that caused this loop'
                        ' was not the timer that was expected: Expected (%s) vs Actual (%s)',
                        expected_timeout_object[0],
                        self.timeout
                    )
                    return
                # This function will only ever by called via the timeout
                # This means that the timeout ran out and can be removed
                self.timeout = None

                async def task_cleanup_wrapper(expected_task: List[asyncio.Task]):
                    # Wrapper function that clears `self.task` member after the loop exits.
                    try:
                        log.debug(
                            'Scheduler loop wrapper starting loop: %s', self.task)
                        await self.loop()
                        # At the end this should be empty,
                        # but during shutdown it might not?
                        if not len(self.lint_queue_high) == 0:
                            log.critical(
                                'Scheduler loop finished with high priority objects still in queue (%i):'
                                ' Did you shut down?', len(
                                    self.lint_queue_high)
                            )
                        if not len(self.lint_queue_low) == 0:
                            log.critical(
                                'Scheduler loop finished with low priority objects still in queue (%i):'
                                ' Did you shut down?', len(self.lint_queue_low)
                            )
                    except Exception:
                        # Becase this function is wrapped inside a task, that is
                        # never awaited, we would lose all exception information!
                        # Capture it here, and ignore it.
                        # Raising it again does not make a difference.
                        log.exception('Exception in scheduler loop')
                    finally:
                        log.debug(
                            'Scheduler loop wrapper finally: Clearing `self.task`: %s', self.task)
                        if any(self.task is not task for task in expected_task):
                            log.critical(
                                'Failed to clean up task because the expected and actual tasks were different:'
                                'Expected (%s) vs Actual (%s)', expected_task[0], self.task)
                            return
                        # Guarantee that the scheduler doesnt get stuck
                        # because the task failed to clean up
                        self.task = None
                # Again wrap the task object and pass it to the cleanup wrapper
                # in order to make sure we clean up the right task object in case of race conditions
                created_task: List[asyncio.Task] = []
                # Start a new loop and remember that it started by writing to self.task
                new_task = asyncio.create_task(
                    task_cleanup_wrapper(created_task))
                created_task.append(new_task)
                self.task = new_task
            # Start a timeout. The loop starting routine will be called
            # if no other files change during the delay period.
            # After that it will run until all files have been handled.
            # After all files have been handled, it will clean itself up
            # and stop. Then a new loop can be started as soon as a user input is made again.
            log.debug('Scheduling scheduler to run in %s',
                      self.delay if delay is None else delay)
            loop = asyncio.get_running_loop()
            # Wrap the timeout in a list and pass to the the scheduler task that created the timeout
            # This makes sure, that we don't have any race conditions somewhere
            expected_timeouts: List[asyncio.TimerHandle] = []
            new_timeout = loop.call_later(
                self.delay if delay is None else delay, create_schedule_loop_task, expected_timeouts)
            expected_timeouts.append(new_timeout)
            self.timeout = new_timeout
        elif starts_loop:
            log.debug(
                'Scheduler would start loop but the condition was not met:'
                ' (success=%s,task=%s)', success, self.task)
        return success
