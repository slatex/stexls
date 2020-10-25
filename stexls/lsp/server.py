from typing import Union, Set, Dict
import logging
import asyncio
import pkg_resources
import sys

from stexls.vscode import *
from stexls.util.random_string import create_random_string
from stexls.util.workspace import Workspace
from stexls.linter import Linter
from stexls.stex import *
from stexls.util.jsonrpc import Dispatcher, method, alias, notification, request

from .completions import CompletionEngine
from .workspace_symbols import WorkspaceSymbols

log = logging.getLogger(__name__)


# pattern_for_environments_that_should_never_display_trefier_annotation_hints = (
#   re.compile('[ma]*(Tr|tr|D|d|Dr|dr)ef[ivx]+s?\*?|gimport\*?|import(mh)?module\*?|symdef\*?|sym[ivx]+\*?'))

class Server(Dispatcher):
    def __init__(
        self,
        connection, *,
        num_jobs: int = 1,
        update_delay_seconds: float = 1.0,
        enable_global_validation: bool = False,
        lint_workspace_on_startup: bool = False,
        enable_linting_of_related_files_on_change: bool = False,
        path_to_trefier_model: Path = None):
        """ Creates a server dispatcher.

        Parameters:
            connection: The connection object required by asyncio processes from the inherited dispatcher class.

        Keyword Arguments:
            num_jobs: Number of processes to use for multiprocessing when compiling.
            update_delay_seconds: Number of seconds the linting of a changed file is delayed after making changes.
            enable_global_validation: Enables linter global validation.
            enable_linting_of_related_files_on_change: Enables automatic linting requests for files that reference a file that received a didChange event.
            lint_workspace_on_startup: Create disagnostics for all files in the workspace after initialization.
            path_to_trefier_model: Path to a loadable Seq2Seq model used to create trefier tags.
        """
        super().__init__(connection=connection)
        self.num_jobs = num_jobs
        self.update_delay_seconds = update_delay_seconds
        self.work_done_progress_capability_is_set: bool = None
        self.enable_global_validation: bool = enable_global_validation
        self.lint_workspace_on_startup: bool = lint_workspace_on_startup
        self.enable_linting_of_related_files_on_change = enable_linting_of_related_files_on_change
        self.path_to_trefier_model = path_to_trefier_model
        # Path to the root directory
        self._root: Path = None
        # trefier model loaded from path_to_trefier_model
        self._trefier_model: 'Seq2SeqModel' = None
        # Event used to prevent the server from answering requests before the server finished initialization
        self._initialized_event: asyncio.Event = asyncio.Event()
        # Workspace instance, used to keep track of file buffers
        self._workspace: Workspace = None
        # Linter instance, used to create diagnostics
        self._linter: Linter = None
        # Completion engine used to encapsulate the complex process of creating completion suggestions
        self._completion_engine: CompletionEngine = None
        # Buffer used to buffer changed files, so that lint isn't called everytime something is typed, but called
        # after a certain delay after the user stopped typing
        self._update_request_buffer: Set[Path] = set()
        # Timeout instance of current update request. Can be canceled when a new update request is made.
        self._update_request_timeout: asyncio.TimerHandle = None
        # Manager for work done progress bars
        self._cancellable_work_done_progresses: Dict[object, ProgressBar] = dict()
        # Accumulator for symbols in workspace, used for suggestions and fast search of missing modules etc
        self._workspace_symbols = WorkspaceSymbols()

    async def _update_files_and_clear_timeout(self):
        ''' Actually update the files in the buffered file update requests.
        '''
        self._update_request_timeout = None
        update_requests = list(self._update_request_buffer)
        self._update_request_buffer.clear()
        log.debug('Linting %i files.', len(update_requests))
        progress_fun = lambda info, count, done: log.debug('Linking "%s": (count=%s, done=%s)', info, count, done)
        cancellable = len(update_requests) > 3
        async with ProgressBar(self, title='Linting', cancellable=cancellable, total=len(update_requests)) as progress:
            self._cancellable_work_done_progresses[progress.token] = progress
            await progress.begin()
            for i, file in enumerate(update_requests):
                await progress.update(i, message=file.name, cancellable=cancellable)
                # TODO: Need all the changed unlinked objects to properly add workspace symbols
                self._workspace_symbols.remove(file)
                ln = self._linter.lint(file, on_progress_fun=progress_fun)
                await self.publish_diagnostics(uri=file.as_uri(), diagnostics=ln.diagnostics)
                obj = self._linter._object_buffer.get(file)
                if obj:
                    self._workspace_symbols.add(obj)
        del self._cancellable_work_done_progresses[progress.token]
        log.debug('Finished linting %i files.', len(update_requests))


    def _request_update_for_set_of_files(self, files: Set[Path]):
        ''' Request update for a set of files.

        The update will be executed after a set amount of time
        and will be delayed again, if @_request_update_for_set_of_files is called again before the timer runs out.
        '''
        log.debug('Update request for the files: %s', files)
        self._update_request_buffer.update(files)
        if self._update_request_timeout:
            log.debug('Canceling old update request timeout: %s', self._update_request_timeout)
            self._update_request_timeout.cancel()
        self._update_request_timeout = asyncio.get_running_loop().call_later(
            self.update_delay_seconds,
            asyncio.create_task,
            self._update_files_and_clear_timeout()
        )
        log.debug('New update timeout: %s', self._update_request_buffer)

    async def __aenter__(self):
        log.debug('Server async enter')

    async def __aexit__(self, *args):
        log.debug('Server async exit args: %s', args)
        log.info('Waiting for update task to finish...')

    @method
    @alias('$/progress')
    def receive_progress(
        self,
        token: ProgressToken,
        value: Union[WorkDoneProgressBegin, WorkDoneProgressReport, WorkDoneProgressEnd]):
        log.info('Progress %s received: %s', token, value)

    @notification
    @alias('$/progress')
    def send_progress(
        self,
        token: ProgressToken,
        value: Union[WorkDoneProgressBegin, WorkDoneProgressReport, WorkDoneProgressEnd]):
        pass

    @method
    def initialize(self, workDoneProgress: ProgressToken = undefined, **params):
        ''' Initializes the serverside.
        This method is called by the client that starts the server.
        The server may only respond to other requests after this method successfully returns.
        '''
        if self._initialized_event.is_set():
            raise RuntimeError('Server already initialized')

        self.work_done_progress_capability_is_set = params.get('capabilities', {}).get('window', {}).get('workDoneProgress', False)
        log.info('Progress information enabled: %s', self.work_done_progress_capability_is_set)

        if 'rootUri' in params and params['rootUri']:
            self._root = Path(urllib.parse.urlparse(params['rootUri']).path)
        elif 'rootPath' in params and params['rootPath']:
            # @rootPath is deprecated and must only be used if @rootUri is not defined
            self._root = Path(params['rootPath'])
        else:
            raise RuntimeError('No root path in initialize.')
        log.info('root at: %s', self._root)

        try:
            version = str(pkg_resources.require('stexls')[0].version)
        except:
            version = 'undefined'
        log.info('stexls version: %s', version)

        return {
            'capabilities': {
                'textDocumentSync': {
                    'openClose': True,
                    'change': 1, # TODO: full=1, incremental=2
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

    def _load_trefier_model(self):
        " Loads the tagger model from the given @self.path_to_trefier_model path and updates self.trefier_model. "
        log.info('Loading trefier model from: %s', self.path_to_trefier_model)
        try:
            try:
                from stexls.trefier.models import Seq2SeqModel
                self._trefier_model: Seq2SeqModel = Seq2SeqModel.load(self.path_to_trefier_model)
            except (ImportError, ModuleNotFoundError):
                pass
        except Exception as err:
            log.exception('Failed to load seq2seq model')
            self.show_message(type=MessageType.Error, message=f'{type(err).__name__}: {err}')

    @method
    async def initialized(self):
        ' Event called by the client after it finished initialization. '
        if self._initialized_event.is_set():
            raise RuntimeError('Server already initialized')
        outdir = self._root / '.stexls' / 'objects'
        self._workspace = Workspace(self._root)
        if self.path_to_trefier_model:
            self._load_trefier_model()
        self._linter = Linter(
            workspace=self._workspace,
            outdir=outdir,
            enable_global_validation=self.enable_global_validation,
            num_jobs=self.num_jobs)
        if self._linter.enable_global_validation:
            compile_progress_iter = self._linter.compile_workspace()
            try:
                async with ProgressBar(server=self, title='Compiling', cancellable=True, total=len(compile_progress_iter)) as progress:
                    self._cancellable_work_done_progresses[progress.token] = progress
                    await progress.begin()
                    for i, currently_compiling_file in enumerate(compile_progress_iter):
                        await progress.update(i, message=currently_compiling_file.name, cancellable=True)
                del self._cancellable_work_done_progresses[progress.token]
            except:
                log.exception('An error occured while compiling workspace')
        self._completion_engine = CompletionEngine(None)
        if self.lint_workspace_on_startup:
            log.info('Linting workspace on startup...')
            files = list(self._linter.workspace.files)
            try:
                async with ProgressBar(server=self, title='Linting', cancellable=True, total=len(files)) as progress:
                    self._cancellable_work_done_progresses[progress.token] = progress
                    await progress.begin()
                    for i, file in enumerate(files):
                        await progress.update(i, message=file.name, cancellable=True)
                        result = self._linter.lint(file)
                        await self.publish_diagnostics(uri=file.as_uri(), diagnostics=result.diagnostics)
                del self._cancellable_work_done_progresses[progress.token]
            except:
                log.exception("Exception raised while linting workspace")
        log.info('Initialized')
        self._initialized_event.set()

    @method
    def shutdown(self):
        log.info('Shutting down server...')

    @method
    def exit(self):
        log.info('exit')
        sys.exit()

    @notification
    @alias('window/showMessage')
    def show_message(self, type: MessageType, message: str):
        pass

    @request
    @alias('window/showMessageRequest')
    def show_message_request(self, type: MessageType, message: str, actions: List[MessageActionItem]):
        pass

    @request
    @alias('window/logMessage')
    def log_message(self, type: MessageType, message: str):
        pass

    @request
    @alias('window/workDoneProgress/create')
    def window_work_done_progress_create(self, token: ProgressToken):
        pass

    @method
    @alias('window/workDoneProgress/cancel')
    def window_work_done_progress_cancel(self, token: ProgressToken):
        log.info('Cancelling work done progress token: %s', token)
        prog = self._cancellable_work_done_progresses.get(token)
        if not prog:
            log.error('Unknown progress token: %s', token)
        if not prog.cancel():
            log.warning('Token already cancelled: %s', token)

    @method
    @alias('textDocument/definition')
    async def definition(
        self,
        textDocument: TextDocumentIdentifier,
        position: Position,
        workDoneToken: ProgressToken = undefined,
        **params):
        await self._initialized_event.wait()
        log.debug('definitions(%s, %s)', textDocument.path, position.format())
        definitions = self._linter.definitions(textDocument.path, position)
        log.debug('Found %i definitions: %s', len(definitions), definitions)
        return definitions

    @method
    @alias('textDocument/references')
    async def references(
        self,
        textDocument: TextDocumentIdentifier,
        position: Position,
        workDoneToken: ProgressToken = undefined,
        context = undefined,
        **params):
        await self._initialized_event.wait()
        log.debug('references(%s, %s)', textDocument.path, position.format())
        references = self._linter.references(textDocument.path, position)
        log.debug('Found %i references: %s', len(references), references)
        return references

    @method
    @alias('textDocument/completion')
    async def completion(
        self,
        textDocument: TextDocumentIdentifier,
        position: Position,
        context: CompletionContext = undefined,
        workDoneToken: ProgressToken = undefined):
        await self._initialized_event.wait()
        log.debug('completion(%s, %s, context=%s)', textDocument.path, position.format(), context)
        return []

    @notification
    @alias('textDocument/publishDiagnostics')
    def publish_diagnostics(self, uri: DocumentUri, diagnostics: List[Diagnostic]):
        pass

    @method
    @alias('textDocument/didOpen')
    async def text_document_did_open(self, textDocument: TextDocumentItem):
        await self._initialized_event.wait()
        log.debug('didOpen(%s)', textDocument)
        if self._workspace.open_file(textDocument.path, textDocument.version, textDocument.text):
            self._request_update_for_set_of_files({textDocument.path})

    @method
    @alias('textDocument/didChange')
    async def text_document_did_change(self, textDocument: VersionedTextDocumentIdentifier, contentChanges: List[TextDocumentContentChangeEvent]):
        # NOTE: Because there is no handler for the annotation type "List": contentChanges is a list of dictionaries!
        await self._initialized_event.wait()
        log.debug('Buffering file "%s" with version %i', textDocument.path, textDocument.version)
        if self._workspace.is_open(textDocument.path):
            for item in contentChanges:
                status = self._workspace.update_file(textDocument.path, textDocument.version, item['text'])
                if not status:
                    log.warning('Failed to patch file with: %s', item)
                else:
                    if self.enable_linting_of_related_files_on_change:
                        log.debug('Linter searching for related files of: "%s"', textDocument.path)
                        requests = self._linter.find_dependent_files_of(textDocument.path)
                        log.debug('Found %i relations: %s', len(requests), requests)
                    else:
                        requests = set()
                    requests.add(textDocument.path)
                    self._request_update_for_set_of_files(requests)
        else:
            log.warning('didCahnge event for non-opened document: "%s"', textDocument.path)


    @method
    @alias('textDocument/didClose')
    async def text_document_did_close(self, textDocument: TextDocumentIdentifier):
        await self._initialized_event.wait()
        log.debug('Closing document: "%s"', textDocument.path)
        status = self._workspace.close_file(textDocument.path)
        if not status:
            log.warning('Failed to close file: "%s"', textDocument.path)

    @method
    @alias('textDocument/didSave')
    async def text_document_did_save(self, textDocument: TextDocumentIdentifier, text: str = undefined):
        await self._initialized_event.wait()
        if self._workspace.is_open(textDocument.path):
            log.info('didSave: %s', textDocument.uri)
            self._request_update_for_set_of_files({textDocument.path})
        else:
            log.debug('Received didSave event for invalid file: %s', textDocument.uri)

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
        self.token = create_random_string(16)
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
        except:
            log.exception('Client refused progress bar creation')
            raise
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        await self.end(self._end_message)
        if exc_type == asyncio.CancelledError:
            log.info('Progressbar cancelled by user input: %s', exc_value)
            return True
        log.exception('An exception occured while a progress bar was running')

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
        created = self._server.window_work_done_progress_create(token=self.token)
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
            args = { }
            if self._title is not None:
                args['title'] = self._title
            if self._total is not None:
                args['percentage'] = 0
            if message is not None:
                args['message'] = message
            begin = WorkDoneProgressBegin(cancellable=self._cancellable, **args)
            await self._server.send_progress(token=self.token, value=begin)
        self._begin_message_sent = True

    async def update(self, iteration_progress_count: int = None, message: str = None, cancellable: bool = None):
        if not self.created:
            # raise ValueError(f'Progress "{self.token}" not created by client.')
            return # Return if not created
        if not self._begin_message_sent:
            raise ValueError('Begin message must be sent before using the progressbar.')
        if self._on_finished_event.cancelled():
            # Raise if canceled
            await self._on_finished_event
        args = { }
        if self._total is not None and iteration_progress_count is not None:
            args['percentage'] = int(100*iteration_progress_count/self._total)
        if message is not None:
            args['message'] = message
        if cancellable is not None:
            args['cancellable'] = cancellable
        report = WorkDoneProgressReport(**args)
        await self._server.send_progress(token=self.token, value=report)

    async def end(self, message: str):
        if not self.created:
            # raise ValueError(f'Progress "{self.token}" not created by client.')
            return # Return if not created
        end = WorkDoneProgressEnd(message=message)
        await self._server.send_progress(token=self.token, value=end)
        if not self._on_finished_event.done():
            # Only set event if not canceled or already returned
            self._on_finished_event.set_result(True)
