''' Implements the server part of the "Tagger Server Protocol" '''
__all__ = ['TaggerServer']
import asyncio
import logging
import sys
from stexls.util.cli import Cli, Arg, command
from stexls.util.jsonrpc import dispatcher
from stexls.util.jsonrpc.tcp import start_server
from stexls.util.jsonrpc.hooks import method
from stexls.util.jsonrpc.protocol import JsonRpcProtocol
from stexls.util.jsonrpc.streams import AsyncBufferedReaderStream, AsyncBufferedWriterStream

from stexls.trefier.models.seq2seq import Seq2SeqModel

log = logging.getLogger(__name__)
model = None

class TaggerServer(dispatcher.Dispatcher):
    @method
    def load_model(self, path: str, force: bool = False):
        global model
        log.info('load_model(%s) called.', path)
        log.debug('Attempting to load model from "%s"', path)
        if not force and model is not None:
            log.debug('Attempt to load a model even though one is already loaded.')
            raise ValueError('Model already loaded.')
        elif force:
            log.debug('Force model load.')
        try:
            model = Seq2SeqModel.load(path)
            log.debug(model.settings)
            return True
        except:
            log.exception('Failed to load model from "%s"', path)
            raise
    
    @method
    def predict(self, *files: str):
        log.info('predict() called.')
        if model is None:
            raise ValueError('No model loaded.')
        log.debug('Predicting for files: %s', files)
        try:
            predictions = model.predict(*files)
            log.debug('Predictions done: %s', predictions)
            return predictions
        except:
            log.exception('Failed to create predictions.')
            raise

    @method
    def get_info(self):
        log.info('get_info() called.')
        if model is None:
            raise ValueError('No model loaded.')
        log.debug('Settings are: %s', model.settings)
        return model.settings

if __name__ == '__main__':
    @command(
        host=Arg(default='localhost', help='Hostname to bind server to.'),
        port=Arg(type=int, default=0, help='Port to bind server on.'),
        loglevel=Arg(default='WARNING', help='Logger loglevel: DEBUG, INFO, WARNING, ERROR, CRITICAL'))
    async def tcp(host: str, port: int, loglevel: str = 'WARNING'):
        ''' Creates a tcp socket server that communicates using json-rcp.
            When the server started accepting messages, a line
            with <hostname>:<port> will be printed to stdout.
        Parameters:
            host: The hostname the server will be launched on.
            port: The port the socket should bind to. 0 for any free port.
            loglevel: Logging loglevel (CRITICAL, ERROR, WARNING, INFO, DEBUG).
        '''
        logging.basicConfig(level=getattr(logging, loglevel.upper(), logging.WARNING))
        log.info('Creating tcp server at %s:%i.', host, port)
        started = asyncio.Future()
        server = asyncio.create_task(
            start_server(TaggerServer, host=host, port=port, started=started))
        info = await started
        print('{}:{}'.format(*info), flush=True)
        await server

    @command(
        loglevel=Arg(default='WARNING', help='Logger loglevel: DEBUG, INFO, WARNING, ERROR, CRITICAL'))
    async def stdio(loglevel: str = 'WARNING'):
        ''' Creates a json-rpc server that listens listens for messages
            using stdin and writes respones to stdout.
            Therefore, only a single client can be connected to this server.
        Parameters:
            loglevel: Logging loglevel (CRITICAL, ERROR, WARNING, INFO, DEBUG).
        '''
        logging.basicConfig(level=getattr(logging, loglevel.upper(), logging.WARNING))
        log.info('Creating json-rpc server using stdin and stdout streams.')
        connection = JsonRpcProtocol(
            AsyncBufferedReaderStream(sys.stdin.buffer),
            AsyncBufferedWriterStream(sys.stdout.buffer))
        server = TaggerServer(connection)
        connection.set_method_provider(server)
        await connection.run_until_finished()
        
    cli = Cli([tcp, stdio], description='Trefier tagger server cli.')
    asyncio.run(cli.dispatch())
    log.info('Server stopped.')