import asyncio
import logging
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Set, Union
from urllib.parse import urlparse

import pkg_resources

from .. import vscode
from ..jsonrpc.dispatcher import Dispatcher
from ..jsonrpc.exceptions import InvalidRequestException
from ..jsonrpc.hooks import alias, method, notification, request
from ..linter.linter import Linter
from ..trefier.models.seq2seq import Seq2SeqModel
from ..util.workspace import Workspace
from .capabilities import WorkDoneProgressCapability
from .completions import CompletionEngine
from .exceptions import ServerNotInitializedException
from .state import ServerState
from .workspace_symbols import WorkspaceSymbols

log = logging.getLogger(__name__)


# pattern_for_environments_that_should_never_display_trefier_annotation_hints = (
#   re.compile('[ma]*(Tr|tr|D|d|Dr|dr)ef[ivx]+s?\*?|gimport\*?|import(mh)?module\*?|symdef\*?|sym[ivx]+\*?'))

class Server(Dispatcher):
    def __init__(
            self,
            connection,
            *,
            num_jobs: int = 1,
            update_delay_seconds: float = 1.0,
            enable_global_validation: bool = False,
            lint_workspace_on_startup: bool = False,
            enable_linting_of_related_files_on_change: bool = False,
            path_to_trefier_model: Path = None):
        """ Creates a server dispatcher.

        Parameters:
            connection: Inherited from Dispatcher. This argument is automatically provided by the class' initialization method.

        Keyword Arguments:
            num_jobs: Number of processes to use for multiprocessing when compiling.
            update_delay_seconds: Number of seconds the linting of a changed file is delayed after making changes.
            enable_global_validation: Enables linter global validation.
            enable_linting_of_related_files_on_change:
                Enables automatic linting requests for files that reference a file that received a didChange event.
            lint_workspace_on_startup: Create disagnostics for all files in the workspace after initialization.
            path_to_trefier_model: Path to a loadable Seq2Seq model used to create trefier tags.
        """
        super().__init__(connection=connection)
        self.state = ServerState.UNINITIALIZED
        self.num_jobs = num_jobs
        self.update_delay_seconds = update_delay_seconds
        self.work_done_progress_capability: WorkDoneProgressCapability = WorkDoneProgressCapability()
        self.enable_global_validation: bool = enable_global_validation
        self.lint_workspace_on_startup: bool = lint_workspace_on_startup
        self.enable_linting_of_related_files_on_change = enable_linting_of_related_files_on_change
        self.path_to_trefier_model = path_to_trefier_model
        # Path to the root directory
        self.rootDirectory: Optional[Path] = None
        # trefier model loaded from path_to_trefier_model
        self.trefier_model: Optional[Seq2SeqModel] = None
        # Workspace instance, used to keep track of file buffers
        self.workspace: Optional[Workspace] = None
        # Linter instance, used to create diagnostics
        self.linter: Optional[Linter] = None
        # Completion engine used to encapsulate the complex process of creating completion suggestions
        self.completion_engine: Optional[CompletionEngine] = None
        # Buffer used to buffer changed files, so that lint isn't called everytime something is typed, but called
        # after a certain delay after the user stopped typing
        self.update_request_buffer: Set[Path] = set()
        # Timeout instance of current update request. Can be canceled when a new update request is made.
        self.update_request_timeout: Optional[asyncio.TimerHandle] = None
        # Manager for work done progress bars
        self.cancellable_work_done_progresses: Dict[object, ProgressBar] = {}
        # Accumulator for symbols in workspace, used for suggestions and fast search of missing modules etc
        self.workspace_symbols = WorkspaceSymbols()

    async def update_files_and_clear_timeout(self):
        ''' Actually update the files in the buffered file update requests.
        '''
        self.update_request_timeout = None
        update_requests = list(self.update_request_buffer)
        self.update_request_buffer.clear()
        log.debug('Linting %i files.', len(update_requests))
        cancellable = len(update_requests) > 3
        async with ProgressBar(self, title='Linting', cancellable=cancellable, total=len(update_requests)) as progress:
            self.cancellable_work_done_progresses[progress.token] = progress
            await progress.begin()
            for i, file in enumerate(update_requests):
                await progress.update(i, message=file.name, cancellable=cancellable)
                # TODO: Need all the changed unlinked objects to properly add workspace symbols
                self.workspace_symbols.remove(file)
                ln = self.linter.lint(file)
                await self.publish_diagnostics(uri=file.as_uri(), diagnostics=ln.diagnostics)
                obj = self.linter._object_buffer.get(file)
                if obj:
                    self.workspace_symbols.add(obj)
        del self.cancellable_work_done_progresses[progress.token]
        log.debug('Finished linting %i files.', len(update_requests))

    def request_update_for_set_of_files(self, files: Set[Path]):
        ''' Request update for a set of files.

        The update will be executed after a set amount of time
        and will be delayed again, if @_request_update_for_set_of_files is called again before the timer runs out.
        '''
        log.debug('Update request for the files: %s', files)
        self.update_request_buffer.update(files)
        if self.update_request_timeout:
            log.debug('Canceling old update request timeout: %s',
                      self.update_request_timeout)
            self.update_request_timeout.cancel()
        self.update_request_timeout = asyncio.get_running_loop().call_later(
            self.update_delay_seconds,
            asyncio.create_task,
            self.update_files_and_clear_timeout()
        )
        log.debug('New update timeout: %s', self.update_request_buffer)

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
    def initialize(
        self,
        capabilities: vscode.ClientCapabilities,
        workspaceFolders: Optional[List[vscode.WorkspaceFolder]] = None,
        processId: Optional[int] = None,
        clientInfo: Optional[Dict[Literal['name', 'version'], str]] = None,
        locale: Optional[str] = None,
        rootPath: Optional[str] = None,
        rootUri: Optional[vscode.DocumentUri] = None,
        initializedOptions: Any = None,
        workDoneProgress: Union[
            int, str, vscode.Undefined] = vscode.undefined,
        initializationOptions: Any = None,
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

        # Work done progress may only be sent if the capability is set
        self.work_done_progress_capability = WorkDoneProgressCapability(
            capabilities.window.get('workDoneProgress', False))
        log.info('Work done progress capability: %s',
                 self.work_done_progress_capability.enabled)

        if isinstance(rootUri, vscode.DocumentUri):
            self.rootDirectory = Path(urlparse(rootUri).path)
        elif isinstance(rootPath, str):
            # rootPath is deprecated and must only be used if @rootUri is not defined
            self.rootDirectory = Path(rootPath)
        else:
            raise RuntimeError('No root path in initialize.')
        log.info('root at: %s', self.rootDirectory)

        if self.path_to_trefier_model:
            log.info('Loading trefier model: %s', self.path_to_trefier_model)
            self.trefier_model = Seq2SeqModel.load(self.path_to_trefier_model)

        try:
            version = str(pkg_resources.require('stexls')[0].version)
        except Exception:
            version = 'undefined'
        log.info('stexls version: %s', version)

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
                'version': version
            }
        }

    def load_trefier_model(self):
        " Loads the tagger model from the given @self.path_to_trefier_model path and updates self.trefier_model. "
        log.info('Loading trefier model from: %s', self.path_to_trefier_model)
        try:
            try:
                from stexls.trefier.models.seq2seq import Seq2SeqModel
                self.trefier_model: Seq2SeqModel = Seq2SeqModel.load(
                    self.path_to_trefier_model)
            except (ImportError, ModuleNotFoundError):
                pass
        except Exception as err:
            log.exception('Failed to load seq2seq model')
            self.show_message(type=vscode.MessageType.Error,
                              message=f'{type(err).__name__}: {err}')

    @method
    async def initialized(self):
        ' Event called by the client after it finished initialization. '
        if self.state == ServerState.UNINITIALIZED:
            raise ServerNotInitializedException()
        if self.state != ServerState.INITIALIZED:
            raise ValueError(
                '`initialized` method can only be called once directly following `initialize`.')
        outdir = self.rootDirectory / '.stexls' / 'objects'
        self.workspace = Workspace(self.rootDirectory)
        if self.path_to_trefier_model:
            self.load_trefier_model()
        self.linter = Linter(
            workspace=self.workspace,
            outdir=outdir,
            enable_global_validation=self.enable_global_validation,
            num_jobs=self.num_jobs)
        if self.linter.enable_global_validation:
            compile_progress_iter = self.linter.compile_workspace()
            try:
                async with ProgressBar(server=self, title='Compiling', cancellable=True, total=len(compile_progress_iter)) as progress:
                    self.cancellable_work_done_progresses[progress.token] = progress
                    await progress.begin()
                    for i, currently_compiling_file in enumerate(compile_progress_iter):
                        await progress.update(i, message=currently_compiling_file.name, cancellable=True)
                del self.cancellable_work_done_progresses[progress.token]
            except Exception:
                log.exception('An error occured while compiling workspace')
        self.completion_engine = CompletionEngine(None)
        if self.lint_workspace_on_startup:
            log.info('Linting workspace on startup...')
            files = list(self.linter.workspace.files)
            try:
                async with ProgressBar(server=self, title='Linting', cancellable=True, total=len(files)) as progress:
                    self.cancellable_work_done_progresses[progress.token] = progress
                    await progress.begin()
                    for i, file in enumerate(files):
                        await progress.update(i, message=file.name, cancellable=True)
                        result = self.linter.lint(file)
                        await self.publish_diagnostics(uri=file.as_uri(), diagnostics=result.diagnostics)
                del self.cancellable_work_done_progresses[progress.token]
            except Exception:
                log.exception("Exception raised while linting workspace")
        log.info('Initialized')
        self.state = ServerState.READY

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
        prog = self.cancellable_work_done_progresses.get(token)
        if not prog:
            log.error('Unknown progress token: %s', token)
        elif not prog.cancel():
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
        if not self.linter:
            return None
        definitions = self.linter.definitions(textDocument.path, position)
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
        if self.state == ServerState.UNINITIALIZED:
            raise ServerNotInitializedException()
        if self.state == ServerState.SHUTDOWN:
            raise InvalidRequestException('The server has shut down')
        log.debug('references(%s, %s)', textDocument.path, position.format())
        if not self.linter:
            return None
        references = self.linter.references(textDocument.path, position)
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
        log.debug('didOpen(%s)', textDocument)
        if not self.workspace:
            return
        if self.workspace.open_file(textDocument.path, textDocument.version, textDocument.text):
            self.request_update_for_set_of_files({textDocument.path})

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
                    textDocument.path, textDocument.version, item['text'])
                if not status:
                    log.warning('Failed to patch file with: %s', item)
                else:
                    if self.linter and self.enable_linting_of_related_files_on_change:
                        log.debug(
                            'Linter searching for related files of: "%s"', textDocument.path)
                        requests = self.linter.find_dependent_files_of(
                            textDocument.path)
                        log.debug('Found %i relations: %s',
                                  len(requests), requests)
                    else:
                        requests = set()
                    requests.add(textDocument.path)
                    self.request_update_for_set_of_files(requests)
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
        if self.workspace and self.workspace.is_open(textDocument.path):
            log.info('didSave: %s', textDocument.uri)
            self.request_update_for_set_of_files({textDocument.path})
        else:
            log.debug('Received didSave event for invalid file: %s',
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
                 end_message: str = None) -> None:
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
        self._total = total
        self._begin_message_sent: bool = False
        self.created: bool = False
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
        if self.created:
            if self._begin_message_sent:
                raise ValueError('ProgressBar begin() called more than once.')
            if self._on_finished_event.cancelled():
                # Raise if canceled
                await self._on_finished_event
            args: Dict[str, Any] = {}
            if self._title is not None:
                args['title'] = self._title
            if self._total is not None:
                args['percentage'] = 0
            if message is not None:
                args['message'] = message
            begin = vscode.WorkDoneProgressBegin(
                cancellable=self._cancellable, **args)
            await self._server.send_progress(token=self.token, value=begin)
        self._begin_message_sent = True

    async def update(self, iteration_progress_count: int = None, message: str = None, cancellable: bool = None):
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
        if self._total is not None and iteration_progress_count is not None:
            args['percentage'] = int(100*iteration_progress_count/self._total)
        if message is not None:
            args['message'] = message
        if cancellable is not None:
            args['cancellable'] = cancellable
        report = vscode.WorkDoneProgressReport(**args)
        await self._server.send_progress(token=self.token, value=report)

    async def end(self, message: str):
        if not self.created:
            # raise ValueError(f'Progress "{self.token}" not created by client.')
            return  # Return if not created
        end = vscode.WorkDoneProgressEnd(message=message)
        await self._server.send_progress(token=self.token, value=end)
        if not self._on_finished_event.done():
            # Only set event if not canceled or already returned
            self._on_finished_event.set_result(True)
