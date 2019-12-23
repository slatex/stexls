''' Implements the server part of the "Tagger Server Protocol" '''
__all__ = ['TaggerServer']
import asyncio
import logging
from stex_language_server.util.cli import Cli, Arg, command
from stex_language_server.util.jsonrpc import tcp
from stex_language_server.util.jsonrpc import dispatcher
from stex_language_server.util.jsonrpc.hooks import method

from stex_language_server.trefier.models.seq2seq import Seq2SeqModel

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
    def server(host: str, port: int, loglevel: str = 'WARNING'):
        logging.basicConfig(level=getattr(logging, loglevel.upper(), logging.WARNING))
        async def async_wrapper():
            log.info('server(%s, %i) called.', host, port)
            started = asyncio.Future()
            server = asyncio.create_task(
                tcp.start_server(TaggerServer, host=host, port=port, started=started))
            info = await started
            print('{}:{}'.format(*info))
            await server
        return asyncio.run(async_wrapper())
        
    cli = Cli([server], description='Trefier tagger server program.')
    cli.dispatch()