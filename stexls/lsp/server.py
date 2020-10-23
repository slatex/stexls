from time import time
from typing import Union, Awaitable, Set, Dict
import logging
import asyncio
import pkg_resources
import sys

from stexls.vscode import *
from stexls.util import create_random_string
from stexls.util.workspace import Workspace
from stexls.linter import Linter
from stexls.stex import *
from stexls.util.jsonrpc import Dispatcher, method, alias, notification, request
from stexls.trefier.models import Seq2SeqModel, Model

from .completions import CompletionEngine

log = logging.getLogger(__name__)


class Server(Dispatcher):
    def __init__(
        self,
        connection, *,
        num_jobs: int = 1,
        update_delay_seconds: float = 1.0,
        enable_global_validation: bool = False,
        lint_workspace_on_startup: bool = False,
        enable_linting_of_related_files_on_change: bool = True,
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
            path_to_trefier_model: Path to a loadable Seq2Seq model used by the compiler in order to create trefier tags.
        """
        super().__init__(connection=connection)
        self.num_jobs = num_jobs
        self.update_delay_seconds = update_delay_seconds
        self.work_done_progress_capability_is_set: bool = None
        self.enable_global_validation: bool = enable_global_validation
        self.lint_workspace_on_startup: bool = lint_workspace_on_startup
        self.enable_linting_of_related_files_on_change = enable_linting_of_related_files_on_change
        self.path_to_trefier_model = path_to_trefier_model
        self._root: Path = None
        self._initialized_event: asyncio.Event = asyncio.Event()
        self._workspace: Workspace = None
        self._linter: Linter = None
        self._completion_engine: CompletionEngine = None
        self._update_requests: Set[Path] = set()
        self._update_request_finished_event: asyncio.Event = None
        self._timeout_start_time: float = None
        self._cancelable_work_done_progresses: Dict[object, asyncio.Future] = dict()

    async def _request_update(self, files: Set[Path]):
        ' Requests an update for the file. '
        # TODO: This can be done better, but works for now...
        log.debug('Update request: %s', files)
        self._update_requests.update(files)
        self._timeout_start_time = time()
        if not self._update_request_finished_event:
            log.debug('Creating request timer')
            self._update_request_finished_event = asyncio.Event()
            while time() - self._timeout_start_time < self.update_delay_seconds:
                log.debug('Waiting for timer to run out...')
                await asyncio.sleep(self.update_delay_seconds)
            log.debug('Linting %i files', len(self._update_requests))
            for file in self._update_requests:
                ln = self._linter.lint(file, on_progress_fun=lambda info, count, done: log.debug('%s %s %s', info, count, done))
                self.publish_diagnostics(uri=ln.uri, diagnostics=ln.diagnostics)
            self._update_requests.clear()
            self._update_request_finished_event.set()
            self._update_request_finished_event = None
        else:
            log.debug('Update request timer already running: Waiting for result for %s', files)
            await self._update_request_finished_event.wait()

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

    def _load_tagger_model(self) -> Optional[Model]:
        " Loads the tagger model from the given @self.path_to_trefier_model path and returns it if successful. "
        log.info('Loading trefier model from: %s', self.path_to_trefier_model)
        try:
            return Seq2SeqModel.load(self.path_to_trefier_model)
        except Exception as err:
            log.exception('Failed to load seq2seq model')
            self.show_message(type=MessageType.Error, message=f'{type(err).__name__}: {err}')
        return None

    @method
    async def initialized(self):
        ' Event called by the client after it finished initialization. '
        if self._initialized_event.is_set():
            raise RuntimeError('Server already initialized')
        outdir = self._root / '.stexls' / 'objects'
        self._workspace = Workspace(self._root)
        model: Seq2SeqModel = None
        if self.path_to_trefier_model:
            model = self._load_tagger_model()
        else:
            log.info('No trefier model has been provided.')
        self._linter = Linter(
            workspace=self._workspace,
            outdir=outdir,
            enable_global_validation=self.enable_global_validation,
            num_jobs=self.num_jobs,
            tagger_model=model)
        if self._linter.enable_global_validation:
            token = None
            cancel: asyncio.Future = None
            if self.work_done_progress_capability_is_set:
                token, cancel = await self._begin_work_done_progress(title='Compiling', cancelable=True)
                log.info('Linter enable_global_validation is enabled: Progress token is "%s"', token)
            compile_progress_iter = self._linter.compile_workspace()
            try:
                for i, currently_compiling_file in enumerate(compile_progress_iter):
                    log.debug('Compile workspace progress (%i/%i): %s', i, len(compile_progress_iter), currently_compiling_file)
                    percentage = int(i*100/len(compile_progress_iter))
                    if self.work_done_progress_capability_is_set:
                        if cancel.cancelled():
                            # Get the exception
                            await cancel
                        report = WorkDoneProgressReport(percentage=percentage, message=currently_compiling_file.name)
                        await self.send_progress(token=token, value=report)
            except asyncio.CancelledError:
                log.info('Cancelled compilation of workspace on startup by user.')
            except:
                log.exception('Exception occured during compiling of workspace')
                raise
            finally:
                if self.work_done_progress_capability_is_set:
                    del self._cancelable_work_done_progresses[token]
                    end = WorkDoneProgressEnd('Compiling workspace done')
                    await self.send_progress(token=token, value=end)
        self._completion_engine = CompletionEngine(None)
        if self.lint_workspace_on_startup:
            log.info('Linting workspace on startup...')
            files = list(self._linter.workspace.files)
            count = len(files)
            token, cancel = None, None
            if self.work_done_progress_capability_is_set:
                token, cancel = await self._begin_work_done_progress(title='Linting', cancelable=True)
            try:
                for i, file in enumerate(files):
                    log.debug('Linting workspace (%i/%i): %s', i, count, file)
                    if self.work_done_progress_capability_is_set:
                        if cancel.cancelled():
                            # Get the cancellation error if is cancelled
                            await cancel
                        report = WorkDoneProgressReport(percentage=int(100*i/count), message=file.name)
                        await self.send_progress(token=token, value=report)
                    result = self._linter.lint(file)
                    await self.publish_diagnostics(uri=file.as_uri(), diagnostics=result.diagnostics)
            except asyncio.CancelledError:
                log.exception('Task %s was cancelled by user input', token)
            except:
                log.exception('Exception raised during linting of workspace')
                raise
            finally:
                if self.work_done_progress_capability_is_set:
                    del self._cancelable_work_done_progresses[token]
                    report = WorkDoneProgressEnd(message=f'Done linting {count} files in workspace')
                    await self.send_progress(token=token, value=report)
        log.info('Initialized')
        self._initialized_event.set()

    async def _begin_work_done_progress(self, title: str, cancelable: bool = False) -> Tuple[str, asyncio.Future]:
        " Creates and begins work done progress. Returns the progress token as well as a cancelable future object if cancelable is True. "
        token = create_random_string(16)
        log.debug('Creating progress token: %s', token)
        await self.window_work_done_progress_create(token=token)
        report = WorkDoneProgressBegin(title=title, cancellable=cancelable)
        await self.send_progress(token=token, value=report)
        if cancelable:
            log.debug('Registering cancelable task: %s', token)
            future = asyncio.Future()
            self._cancelable_work_done_progresses[token] = future
            return token, future
        return token

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
        prog = self._cancelable_work_done_progresses.get(token)
        if not prog:
            log.error('Unknown progress token: %s', token)
        elif not prog.cancelled():
            prog.cancel()
        else:
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
            await self._request_update({textDocument.path})

    @method
    @alias('textDocument/didChange')
    async def text_document_did_change(self, textDocument: VersionedTextDocumentIdentifier, contentChanges: List[TextDocumentContentChangeEvent]):
        await self._initialized_event.wait()
        log.debug('updating file "%s" with version %i', textDocument.path, textDocument.version)
        if self._workspace.is_open(textDocument.path):
            for item in contentChanges:
                status = self._workspace.update_file(textDocument.path, textDocument.version, item['text'])
                if not status:
                    log.warning('Failed to patch file with: %s', item)
                else:
                    if self.enable_linting_of_related_files_on_change:
                        requests = self._linter.find_dependent_files_of(textDocument.path)
                    else:
                        requests = set()
                    requests.add(textDocument.path)
                    await self._request_update(requests)
        else:
            log.warning('did_change event for non-opened document: "%s"', textDocument.path)


    @method
    @alias('textDocument/didClose')
    async def text_document_did_close(self, textDocument: TextDocumentIdentifier):
        await self._initialized_event.wait()
        log.debug('Closing document: "%s"', textDocument.path)
        status = self._workspace.close_file(textDocument.path)
        if not status:
            log.warning('Failed to close file "%s"', textDocument.path)

    @method
    @alias('textDocument/didSave')
    async def text_document_did_save(self, textDocument: TextDocumentIdentifier, text: str = undefined):
        await self._initialized_event.wait()
        if self._workspace.is_open(textDocument.path):
            log.info('didSave: %s', textDocument.uri)
            await self._request_update({textDocument.path})
        else:
            log.debug('Received didSave event for invalid file: %s', textDocument.uri)
