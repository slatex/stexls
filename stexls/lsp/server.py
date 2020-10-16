from time import time
from typing import Union, Awaitable, Set
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

from .completions import CompletionEngine

log = logging.getLogger(__name__)


class Server(Dispatcher):
    def __init__(self, connection, *, num_jobs: int = 1, update_delay_seconds: float = 1.0, enable_global_validation: bool = False):
        """ Creates a server dispatcher.

        Parameters:
            connection: The connection object required by asyncio processes from the inherited dispatcher class.

        Keyword Arguments:
            num_jobs: Number of processes to use for multiprocessing when compiling.
            update_delay_seconds: Number of seconds the linting of a changed file is delayed after making changes.
            enable_global_validation: Enables linter global validation.
        """
        super().__init__(connection=connection)
        self.num_jobs = num_jobs
        self.update_delay_seconds = update_delay_seconds
        self.work_done_progress_capability_is_set: bool = None
        self.enable_global_validation: bool = enable_global_validation
        self._root: Path = None
        self._initialized_event: asyncio.Event = asyncio.Event()
        self._workspace: Workspace = None
        self._linter: Linter = None
        self._completion_engine: CompletionEngine = None
        self._update_requests: Set[Path] = set()
        self._update_request_finished_event: asyncio.Event = None
        self._timeout_start_time: float = None

    async def _request_update(self, file: Path):
        ' Requests an update for the file. '
        log.debug('Update request: "%s"', file)
        self._update_requests.add(file)
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
            log.debug('Update request timer already running: Waiting for result for "%s"', file)
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

    @method
    async def initialized(self):
        ' Event called by the client after it finished initialization. '
        if self._initialized_event.is_set():
            raise RuntimeError('Server already initialized')
        outdir = self._root / '.stexls' / 'objects'
        self._workspace = Workspace(self._root)
        self._linter = Linter(
            workspace=self._workspace,
            outdir=outdir,
            enable_global_validation=self.enable_global_validation,
            num_jobs=self.num_jobs)
        if self._linter.enable_global_validation:
            token = create_random_string(16)
            log.info('Linter enable_global_validation is enabled: Progress token is "%s"', token)
            if self.work_done_progress_capability_is_set:
                log.info('Client has workDoneProgerss enabled.')
                await self.window_work_done_progress_create(token=token)
            else:
                log.warning('Client does NOT have workDoneProgress enabled: No work done progress info will be sent!')
            compile_progress_iter = self._linter.compile_workspace()
            if self.work_done_progress_capability_is_set:
                begin = WorkDoneProgressBegin('Compiling', message=f'{len(compile_progress_iter)} files in workspace', cancellable=False)
                await self.send_progress(token=token, value=begin)
            try:
                for i, currently_compiling_file in enumerate(compile_progress_iter):
                    log.debug('Compile workspace progress: "%s" (%i/%i)', currently_compiling_file, i, len(compile_progress_iter))
                    percentage = int(i*100/len(compile_progress_iter))
                    if self.work_done_progress_capability_is_set:
                        report = WorkDoneProgressReport(percentage=percentage, message=currently_compiling_file.name)
                        await self.send_progress(token=token, value=report)
            finally:
                if self.work_done_progress_capability_is_set:
                    end = WorkDoneProgressEnd('Compiling workspace done')
                    await self.send_progress(token=token, value=end)
        self._completion_engine = CompletionEngine(None)
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
        log.warning('Client attempted to cancel token %s, but canceling is not implemented yet', token)

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
            await self._request_update(textDocument.path)

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
                    await self._request_update(textDocument.path)
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
        else:
            log.debug('Received didSave event for invalid file: %s', textDocument.uri)
