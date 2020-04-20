import logging
import pkg_resources
import sys
import pickle
import functools
from pathlib import Path
import urllib

from stexls.stex import Linker, Compiler
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
    @method
    def initialize(self, **params):
        if self._initialized:
            raise ValueError('Server already initialized')
        return {
            'capabilities': {
                'textDocumentSync': {
                    'openClose': True,
                    'change': 1, # TODO: full=1, incremental=2
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
    def initialized(self):
        if self._initialized:
            raise ValueError('Server already initialized')
        self._initialized = True
        root = Path.cwd()
        outdir = root / '.stexls' / 'objects'
        self._workspace = Workspace(root)
        self._compiler = Compiler(self._workspace, outdir)
        self._linker = Linker(root)
        # objects = self._compiler.compile(self._workspace.files)
        # self._linker.link(objects, self._compiler.modules)
        log.info('Initialized: %s')

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

    @method
    @alias('textDocument/definition')
    def definition(self, textDocument: TextDocumentIdentifier, position: Position, **params):
        log.info('get definition of document %s at position %s with context %s', textDocument, position, params)
        raise NotImplementedError

    @method
    @alias('textDocument/references')
    def references(self, textDocument: TextDocumentIdentifier, position: Position, context):
        log.info('get references of document %s at position %s with context %s', textDocument, position, context)
        raise NotImplementedError

    @method
    @alias('textDocument/didOpen')
    def text_document_did_open(self, textDocument: TextDocumentItem):
        log.info('text document close: %s', textDocument)
        self._workspace.open_file(textDocument.path, textDocument.text)

    @method
    @alias('textDocument/didChange')
    def text_document_did_change(self, **params):
        log.info('text document change: %s', params)

    @method
    @alias('textDocument/didClose')
    def text_document_did_close(self, textDocument: TextDocumentItem):
        log.info('text document close: %s', textDocument)
        self._workspace.close_file(textDocument.path)
        self._compiler.delete_objectfiles(textDocument.path)
