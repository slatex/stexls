import logging
import pkg_resources
import sys
import pickle
import functools
import random
import string
import asyncio
from pathlib import Path
import urllib
import time
from typing import Callable, Dict, Set


from stexls.stex import Linker, Compiler, StexObject, Symbol
from stexls.util.workspace import Workspace
from stexls.util.jsonrpc import *
from stexls.util.vscode import *
from .completions import CompletionEngine

log = logging.getLogger(__name__)


class Server(Dispatcher):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._initialized = False
        self._workspace: Workspace = None
        self._compiler: Compiler = None
        self._linker: Linker = None
        self._root = None
        self._completion_engine: CompletionEngine = None
        self.progressEnabled = False

    @method
    @alias('$/progress')
    def receive_progress(self, token: ProgressToken, value: Union[WorkDoneProgressBegin, WorkDoneProgressReport, WorkDoneProgressEnd]):
        log.info('Progress %s received: %s', token, value)

    @notification
    @alias('$/progress')
    def send_progress(self, token: ProgressToken, value: Union[WorkDoneProgressBegin, WorkDoneProgressReport, WorkDoneProgressEnd]):
        pass

    @method
    def initialize(self, workDoneProgress: ProgressToken = undefined, **params):
        if self._initialized:
            raise ValueError('Server already initialized')
        self.progressEnabled = params.get('capabilities', {}).get('window', {}).get('workDoneProgress', False)
        log.debug('workDoneProgress: %s', workDoneProgress)
        log.info('progressEnabled: %s', self.progressEnabled)
        if 'rootUri' in params and params['rootUri']:
            self._root = Path(urllib.parse.urlparse(params['rootUri']).path)
        elif 'rootPath' in params and params['rootPath']:
            self._root = Path(params['rootPath'])
        else:
            raise ValueError(f'No root path in initialize.')
        log.info('root at: %s', self._root)
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
                'version': str(pkg_resources.require('stexls')[0].version)
            }
        }

    @method
    async def initialized(self):
        if self._initialized:
            raise ValueError('Server already initialized')
        outdir = self._root / '.stexls' / 'objects'
        self._workspace = Workspace(self._root)
        self._compiler = Compiler(self._workspace, outdir)
        self._linker = Linker(self._root)
        self._completion_engine = CompletionEngine(self._linker)
        await self._update(all=True)
        log.info('Initialized')
        self._initialized = True

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
    def definition(
        self,
        textDocument: TextDocumentIdentifier,
        position: Position,
        workDoneToken: ProgressToken = undefined,
        **params):
        symbols: List[Tuple[Range, Symbol]] = self._linker.definitions(textDocument.path, position.line, position.character)
        log.debug('Found %i symbols at %s', len(symbols), position)
        return [
            LocationLink(
                targetUri=symbol.location.uri,
                targetRange=symbol.location.range,
                targetSelectionRange=symbol.location.range,
                originSelectionRange=original_selection_range)
            for original_selection_range, symbol in symbols
        ]

    @method
    @alias('textDocument/references')
    def references(
        self,
        textDocument: TextDocumentIdentifier,
        position: Position,
        workDoneToken: ProgressToken = undefined,
        context = undefined,
        **params):
        symbols: List[Tuple[Range, Symbol]] = self._linker.definitions(textDocument.path, position.line, position.character)
        log.debug('Searching for references of these symbols: %s', list(s for _, s in symbols))
        references: List[Location] = []
        for _, symbol in symbols:
            references.extend(self._linker.references(symbol))
        log.debug('Found %i references at %s', len(references), position)
        return references

    @method
    @alias('textDocument/completion')
    def completion(
        self,
        textDocument: TextDocumentIdentifier,
        position: Position,
        context: CompletionContext = undefined,
        workDoneToken: ProgressToken = undefined):
        log.info('completion invoked: %s', workDoneToken)
        path = textDocument.path
        lines = self._workspace.read_file(path).split('\n')
        completions = self._completion_engine.completion(path, lines , position)
        return completions

    @notification
    @alias('textDocument/publishDiagnostics')
    def publish_diagnostics(self, uri: DocumentUri, diagnostics: List[Diagnostic]):
        pass

    def _create_diagnostics(self, link: StexObject) -> List[Diagnostic]:
        diagnostics: List[Diagnostic] = []
        for location, errors in link.errors.items():
            for error in errors:
                range = location.range
                if 0 == location.range.start.character:
                    range = range.translate(0, 1)
                    range.end.character -= 1
                if 0 == location.range.end.character:
                    range = range.translate(0, 1)
                errname = type(error).__name__.lower()
                if 'info' in errname:
                    severity = DiagnosticSeverity.Information
                elif 'warning' in errname:
                    severity = DiagnosticSeverity.Warning
                else:
                    severity = DiagnosticSeverity.Error
                diagnostic = Diagnostic(
                    range=location.range,
                    message=str(error),
                    severity=severity)
                diagnostics.append(diagnostic)
        return diagnostics

    @method
    @alias('textDocument/didOpen')
    async def text_document_did_open(self, textDocument: TextDocumentItem):
        if self._workspace.open_file(textDocument.path, textDocument.text):
            log.info('didOpen: %s', textDocument.uri)
            await self._request_file_update(textDocument.path)
        else:
            log.debug('Received didOpen event for invalid file: %s', textDocument.uri)

    @method
    @alias('textDocument/didChange')
    async def text_document_did_change(self, textDocument: VersionedTextDocumentIdentifier, contentChanges: List[dict]):
        for change in contentChanges:
            if not self._workspace.open_file(textDocument.path, change['text']):
                return
        log.info('didChange: "%s" (%i change(s)).', textDocument.uri, len(contentChanges))
        await self._request_file_update(textDocument.path)

    @method
    @alias('textDocument/didClose')
    def text_document_did_close(self, textDocument: TextDocumentIdentifier):
        if self._workspace.close_file(textDocument.path):
            log.info('didClose: %s', textDocument.uri)
            self._compiler.delete_objectfiles([textDocument.path])
        else:
            log.debug('Received didClose event for invalid file: %s', textDocument.uri)

    @method
    @alias('textDocument/didSave')
    async def text_document_did_save(self, textDocument: TextDocumentIdentifier, text: str = undefined):
        if self._workspace.is_open(textDocument.path):
            log.info('didSave: %s', textDocument.uri)
            await self._request_file_update(textDocument.path)
        else:
            log.debug('Received didSave event for invalid file: %s', textDocument.uri)

    async def _request_file_update(self, path: Path):
        """ Sends off a request that a file path needs to be linked again and returns an awaitable that resolves after the file was linked. """
        # reset the time the last request was sent
        self._time_update_requested = time.time()
        if path not in self._link_requests:
            # add file to queue
            log.debug('Requested update for file: %s', path)
            self._link_requests.add(path)
        # wait for the next update cycle to finish
        await self._background_linker_finished_event.wait()

    async def _update(self, all: bool = False, files: List[Path] = None):
        """ Compiles and links files.

        After the set of files to compile is determined according to the parameters,
        the linker will link them and diagnostics are published for each of the files.
        Parameters:
            all: If true, all files in the workspace are getting linked. If no specific files are provided, then all modified files are linked.
            files: If given, only those files are linked.
        """
        loop = asyncio.get_event_loop()
        if files is None:
            files = self._workspace.files
        if not all:
            files = self._compiler.modified(files)
        try:
            async with WorkDoneProgressManager(self) as progressfn:
                objects = await loop.run_in_executor(
                    None,
                    self._compiler.compile,
                    files,
                    progressfn('Compiling'),
                    True)
                log.debug('Compiled: %s', set(objects))
                links = await loop.run_in_executor(
                    None,
                    self._linker.link,
                    objects,
                    self._compiler.modules,
                    progressfn,
                    False)
                for obj, link in links.items():
                    self.publish_diagnostics(uri=obj.path.as_uri(), diagnostics=self._create_diagnostics(link))
        except:
            log.exception('Failed to create progress')

    async def _background_file_linker(self, freq: float = 1.0):
        """ An infinite loop that periodically links files. The files to update can be requested using request_file_update(). """
        while True:
            # repeat until time since last update is freq seconds old
            if time.time() - self._time_update_requested > freq:
                log.debug('%i link requests queued.', len(self._link_requests))
                if self._link_requests:
                    # buffer flagged files
                    files = list(self._link_requests)
                    # delete the queue
                    self._link_requests.clear()
                    # buffer the associated event
                    event = self._background_linker_finished_event
                    # reset the event
                    self._background_linker_finished_event = asyncio.Event()
                    # update all files added in the meantime
                    await self._update(files=files)
                    # signal that files were updated
                    event.set()
            # yield to other threads while the time difference is not large enough
            await asyncio.sleep(freq)

    async def __aenter__(self):
        log.debug('Server async enter called')
        self._time_update_requested = 0
        self._link_requests: Set[str] = set()
        self._background_linker_finished_event = asyncio.Event()
        self._background_file_linker_task = asyncio.create_task(self._background_file_linker())
    
    async def __aexit__(self, *args):
        log.debug('Server async exit called')
        self._background_file_linker_task.cancel()


class WorkDoneProgressManager:
    def __init__(self, server: Server, freq: float = 1.0):
        self.server = server
        self.freq = freq
        self.token = None
        self.titles = []
        self.title = None
        self.index = 0
        self.percentage = undefined
        self.message = undefined

    async def _updater(self):
        if not self.server.progressEnabled:
            log.warning('Client has progress information not enabled: Skipping')
        while self.server.progressEnabled:
            if self.index < len(self.titles):
                if self.token is not None:
                    log.debug('Ending progress on token %s', self.token)
                    self.server.send_progress(token=self.token, value=WorkDoneProgressEnd())
                    self.token = None
                self.title = self.titles[self.index]
                self.percentage = undefined
                if self.title is None:
                    return
                self.token = ''.join(random.sample(string.ascii_letters, len(string.ascii_letters)))
                self.index += 1
                log.debug('Creating new progress %s (%s)', self.title, self.token)
                await self.server.window_work_done_progress_create(token=self.token)
                self.server.send_progress(token=self.token, value=WorkDoneProgressBegin(title=self.title))
            elif self.token:
                self.server.send_progress(token=self.token, value=WorkDoneProgressReport(percentage=self.percentage, message=self.message))
            await asyncio.sleep(self.freq)

    def __call__(self, title: str) -> Callable[[Iterable], Iterable]:
        log.debug('Creating progress wrapper: %s', title)
        self.titles.append(title)
        def wrapper(it):
            length = None
            if hasattr(it, '__len__'):
                length = len(it)
                log.debug('Progress wrapper iterating over %i elements', length)
            else:
                log.debug('Progress wrapper iterating over iterator')
            for i, el in enumerate(it):
                if length:
                    self.percentage = int(round(i*100/length))
                    self.message = f'{self.percentage}%'
                else:
                    self.message = f'{i} of ?'
                yield el
        return wrapper

    async def __aenter__(self):
        self.updater = asyncio.create_task(self._updater())
        return self

    async def __aexit__(self, *args):
        log.debug('Sending pill to updater task.')
        self.titles.append(None)
        await self.updater
        log.debug('Progress manager udpater finished successfully.')