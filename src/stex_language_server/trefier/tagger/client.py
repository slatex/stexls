''' Implements the "Tagger Server Protocol" client. '''
__all__ = ['TaggerClient']
import asyncio
import logging
from stex_language_server.util.cli import Cli, Arg, command
from stex_language_server.util.jsonrpc import tcp
from stex_language_server.util.jsonrpc import dispatcher
from stex_language_server.util.jsonrpc.hooks import request, notification

from stex_language_server.trefier.models.seq2seq import Seq2SeqModel

log = logging.getLogger(__name__)

class TaggerClient(dispatcher.Dispatcher):
    @request
    def load_model(self, path: str, force: bool = False) -> bool: pass
    @request
    def predict(self, *files: str): pass
    @request
    def get_info(self): pass

if __name__ == '__main__':
    @command(
        host=Arg(default='localhost', help='IP of the server.'),
        port=Arg(type=int, default=0, help='Port of the server.'),
        loglevel=Arg(default='WARNING', help='Logger loglevel: DEBUG, INFO, WARNING, ERROR, CRITICAL'))
    def client(host: str, port: int, loglevel: str = 'WARNING'):
        logging.basicConfig(level=getattr(logging, loglevel.upper(), logging.WARNING))
        async def async_wrapper():
            log.info('client(%s, %i) called.', host, port)
            dispatcher = asyncio.Future()
            client = asyncio.create_task(
                tcp.open_connection(TaggerClient, host=host, port=port, connection=dispatcher))
            dispatcher = await dispatcher
            await client 
        return asyncio.run(async_wrapper())
        
    cli = Cli([client], description='Trefier tagger client program.')
    cli.dispatch()
