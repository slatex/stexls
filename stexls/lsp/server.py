import logging
import pkg_resources
import sys
import pickle
import functools
from pathlib import Path
import urllib

from stexls.stex import Linker
from stexls.util.jsonrpc import *
from stexls.util.vscode import *

log = logging.getLogger(__name__)


class Server(Dispatcher):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._initialized = False
        self._cache = None
        self._linker = None
        self._root = None

    def load_or_create_state(self):
        self._linker = None
        if self._cache.is_file():
            try:
                log.debug('Attempting to load state from cachefile at "%s"', self._cache)
                with open(self._cache, 'rb') as fd:
                    self._linker = pickle.load(fd)
            except:
                log.exception('Failed to load server state from cachefile: "%s"', self._cache)
        if self._linker is None:
            log.debug('Creating new linker at root "%s"', self._root)
            self._linker = Linker(root=self._root, file_pattern='**/smglom/**/*.tex')

    def savestate(self):
        log.info('Saving state to file: "%s"', self._cache)
        with open(self._cache, 'wb') as fd:
            pickle.dump(self._linker, fd)

    @method
    def initialize(self, **kparams):
        if self._initialized:
            raise ValueError('Server already initialized')
        log.info('initialize')
        return {
            'capabilities': {
                'definitionProvider': True,
                'referencesProvider': True,
                # 'documentSymbolProvider': True,
                # 'workspaceSymbolProvider': True,
                # 'workspace': { 'workspaceFolders' }
            },
            'serverInfo': {
                'name': 'stexls',
                'version': str(pkg_resources.require('stexls')[0].version)
            }
        }
    
    @method
    def initialized(self, *params, **kparams):
        if self._initialized:
            raise ValueError('Server already initialized')
        self._initialized = True
        self._root = Path.cwd()
        self._cache = self._root / 'stexls-cache.bin'
        self.load_or_create_state()
        def progfn(it, title):
            try:
                log.info("%s: %i", title, len(it))
            except:
                log.exception(title)
            yield from it
        self._linker.update(progfn)
        return self.show_message_request(1, "This is a message!", [])

    @method
    def shutdown(self):
        log.info('Shutting down server...')
        # store the state
        self.savestate()
        # make unusable in case something wants to change the sate after it was stored
        self._linker = None
        self._cache = None
        self._root = None

    @method
    def exit(self):
        log.info('exit')
        sys.exit()

    @method
    @alias('$/cancelRequest')
    def cancel_request(self, id: int):
        log.info('Received cancel request for: %s', id)

    @method
    @alias('$/progress')
    def receive_progress(self, token: ProgressToken, value):
        pass

    @notification
    @alias('$/progress')
    def send_progress(self, token: ProgressToken, value):
        pass
    
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
        path = Path(urllib.parse.urlparse(textDocument['uri']).path)
        log.info('get definition of document %s at position %s with context %s', path, position, params)
        return [
            LocationLink(
                targetUri=str(symbol.location.uri.as_uri()),
                targetRange=symbol.location.range,
                targetSelectionRange=symbol.location.range,
                originalSelectionRange=referenceRange).to_json()
            for referenceRange, symbol
            in self._linker.get_definitions(
                path,
                position['line'],
                position['character']
            )
        ]

    @method
    @alias('textDocument/references')
    def references(self, textDocument, position, context):
        log.info('get references of document %s at position %s with context %s', textDocument, position, context)
        raise NotImplementedError
