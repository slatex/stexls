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
from typing import Callable


from stexls.stex import Linker, Compiler, StexObject
from stexls.util.workspace import Workspace
from stexls.util.jsonrpc import *
from stexls.util.vscode import *

log = logging.getLogger(__name__)


class Server(Dispatcher):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._initialized = False
        self._workspace: Workspace = None
        self._compiler: Compiler = None
        self._linker: Linker = None
        self._root = None

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
                },
                'completionProvider': {
                    'triggerCharacters': ['?', '[', '{', ',', '='],
                    'allCommitCharacters': [']', '}', ','],
                    'resolveProvider': True,
                    'workDoneProgress': True
                },
                'definitionProvider': {
                    'workDoneProgress': True
                },
                'referencesProvider': {
                    'workDoneProgress': True
                },
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

    async def _update(self, all: bool = False, specific_files: List[DocumentUri] = None):
        try:
            loop = asyncio.get_event_loop()
            if specific_files:
                files = [Path(url.path) for url in map(urllib.parse.urlparse, specific_files)]
            else:
                files = self._workspace.files
                if not all:
                    files = self._compiler.modified(files)
            async with ProgressManager(self) as progressfn:
                objects = await loop.run_in_executor(
                    None,
                    self._compiler.compile,
                    files,
                    progressfn('Compiling'),
                    False)
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

    @method
    async def initialized(self):
        if self._initialized:
            raise ValueError('Server already initialized')
        outdir = self._root / '.stexls' / 'objects'
        self._workspace = Workspace(self._root)
        self._compiler = Compiler(self._workspace, outdir)
        self._linker = Linker(self._root)
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
        log.info('get definition: %s', workDoneToken)
        raise NotImplementedError

    @method
    @alias('textDocument/references')
    def references(
        self,
        textDocument: TextDocumentIdentifier,
        position: Position,
        workDoneToken: ProgressToken = undefined,
        context = undefined,
        **params):
        log.info('get references: %s', workDoneToken)
        raise NotImplementedError

    @method
    @alias('textDocument/completion')
    def completion(
        self,
        textDocument: TextDocumentIdentifier,
        position: Position,
        context: CompletionContext = undefined,
        workDoneToken: ProgressToken = undefined):
        log.info('completion invoked: %s', workDoneToken)
        raise NotImplementedError

    @notification
    @alias('textDocument/publishDiagnostics')
    def publish_diagnostics(self, uri: DocumentUri, diagnostics: List[Diagnostic]):
        pass

    def _create_diagnostics(self, link: StexObject) -> List[Diagnostic]:
        diagnostics: List[Diagnostic] = []
        for location, errors in link.errors.items():
            for error in errors:
                diagnostic = Diagnostic(
                    range=location.range,
                    message=str(error),
                    severity=DiagnosticSeverity.Warning if 'Warning' in type(error).__name__ else DiagnosticSeverity.Error)
                diagnostics.append(diagnostic)
        return diagnostics

    @method
    @alias('textDocument/didOpen')
    async def text_document_did_open(self, textDocument: TextDocumentItem):
        log.info('text document close: %s', textDocument)
        self._workspace.open_file(textDocument.path, textDocument.text)
        await self._update(specific_files=[textDocument.uri])

    @method
    @alias('textDocument/didChange')
    async def text_document_did_change(self, textDocument: VersionedTextDocumentIdentifier, contentChanges: List[dict]):
        log.info('text document "%s" changed (%i change(s)).', textDocument.path, len(contentChanges))
        for change in contentChanges:
            if not self._workspace.open_file(textDocument.path, change['text']):
                return
        await self._update(specific_files=[textDocument.uri])

    @method
    @alias('textDocument/didClose')
    def text_document_did_close(self, textDocument: TextDocumentIdentifier):
        log.info('text document close: %s', textDocument)
        if self._workspace.close_file(textDocument.path):
            self._compiler.delete_objectfiles(textDocument.path)


class ProgressManager:
    def __init__(self, server: Server, freq: float = 1.0):
        self.server = server
        self.freq = freq
        self.token = None
        self.titles = []
        self.title = None
        self.index = 0
        self.percentage = undefined
        self.message = undefined
        self.updater = asyncio.create_task(self._updater())

    async def _updater(self):
        if not self.server.progressEnabled:
            log.warning('Client has progress information not enabled: Skipping')
        while self.server.progressEnabled:
            log.debug('Progress manager update')
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
        return self

    async def __aexit__(self, *args):
        log.debug('Sending pill to updater task.')
        self.titles.append(None)
        await self.updater
        log.debug('Progress manager udpater finished successfully.')