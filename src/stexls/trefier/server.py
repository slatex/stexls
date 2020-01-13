''' Implements the server side of the tagger using the json rpc protocol.
    This module contains the dispatcher which provides the methods
    for a JsonRpcProtocol.
    Furthermore, if this module is run as __main__, it can
    start a server using tcp or read and write json-rpc messages directly
    from stdin/out.
'''
__all__ = ['TaggerServerDispatcher']

import asyncio
import logging
from typing import List, Dict, Any
from stexls.trefier.models.tags import Tag
from stexls.trefier.models.base import Model
from stexls.util.cli import Cli, Arg, command
from stexls.util.jsonrpc import dispatcher
from stexls.util.jsonrpc.hooks import method
from stexls.trefier.models.seq2seq import Seq2SeqModel

log = logging.getLogger(__name__)

class TaggerServerDispatcher(dispatcher.Dispatcher):
    ''' This is the interface the tagger server implements. '''
    model: Model = None
    @method
    def load_model(self, path: str, force: bool = False) -> Dict[str, Any]:
        """Loads a model backend.

        Args:
            path (str): Path to saved model.
            force (bool, optional): Allows loading if a model is already loaded. Defaults to False.

        Raises:
            ValueError: Model already loaded and force is not set.
            ValueError: Model.load(path) returned None.

        Returns:
            Dict[str, Any]: Loaded model information.
        """
        TaggerServerDispatcher.model
        log.info('load_model(%s, %s)', path, force)
        if not force and TaggerServerDispatcher.model is not None:
            log.debug('Attempt to load a model even though one is already loaded.')
            raise ValueError('Model already loaded.')
        try:
            TaggerServerDispatcher.model = Seq2SeqModel.load(path)
            if TaggerServerDispatcher.model is None:
                log.error('load_model(%s) returned None because of unknown reason.')
                raise ValueError('Failed to load model because of unknown reason.')
            log.debug('Loaded model from "%s" has settings: %s', path, TaggerServerDispatcher.model.settings)
            return TaggerServerDispatcher.model.settings
        except:
            log.exception('Failed to load model from "%s"', path)
            raise

    @method
    def predict(self, *files: str) -> List[List[Tag]]:
        """Creates a list of tags for each provided file.

        Raises:
            ValueError: No model loaded using load_model()

        Returns:
            List[List[Tag]]: A list of tags for each file.
        """
        log.info('predict(%s)', files)
        if TaggerServerDispatcher.model is None:
            raise ValueError('No model loaded.')
        try:
            predictions = TaggerServerDispatcher.model.predict(*files)
            log.debug('Predictions: %s', predictions)
            return predictions
        except:
            log.exception('Failed to create predictions.')
            raise

    @method
    def get_info(self) -> Dict[str, Any]:
        """Gets info about the loaded model.

        Raises:
            ValueError: No model loaded.

        Returns:
            Dict[str, Any]: Model information.
        """
        log.info('get_info()')
        if TaggerServerDispatcher.model is None:
            raise ValueError('No model loaded.')
        log.debug('Settings are: %s', TaggerServerDispatcher.model.settings)
        return TaggerServerDispatcher.model.settings


if __name__ == '__main__':
    @command(
        host=Arg(default='localhost', help='Hostname to bind server to.'),
        port=Arg(type=int, default=0, help='Port to bind server on.'),
        loglevel=Arg(default='error', choices=['error', 'warning', 'info', 'debug'], help='Logger loglevel.'))
    async def tcp(host: str, port: int, loglevel: str = 'error'):
        """ Creates a tcp socket server that communicates using json-rcp.

        When the server started accepting messages, a line
        with <hostname>:<port> will be printed to stdout.

        Args:
            host (str): Server hostname.
            port (int): Server port. "0" for any free port.
            loglevel (str, optional): Loglevel (error, warning, info, debug). Defaults to 'error'.
        """
        logging.basicConfig(level=getattr(logging, loglevel.upper(), logging.WARNING))
        log.info('Creating tcp server at %s:%i.', host, port)
        (host, port), server = await dispatcher.start_server(TaggerServerDispatcher, host, port)
        print('{}:{}'.format(host, port), flush=True)
        await server

    @command(
        loglevel=Arg(default='error', choices=['error', 'warning', 'info', 'debug'], help='Logger loglevel.'))
    async def stdio(loglevel: str = 'error'):
        """Starts a tagger json-rpc server reading from stdin and writing to stdout.

        Args:
            loglevel (str, optional): Logging level (error, warning, info, debug). Defaults to 'error'.
        """
        logging.basicConfig(level=getattr(logging, loglevel.upper(), logging.WARNING))
        log.info('Creating json-rpc server using stdin and stdout streams.')
        _, server = await dispatcher.open_stdio_connection(TaggerServerDispatcher)
        await server

    cli = Cli([tcp, stdio], description=__doc__)
    try:
        asyncio.run(cli.dispatch())
    finally:
        log.info('Server stopped.')
