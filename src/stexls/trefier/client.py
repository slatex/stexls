''' This module implements the client side of the
    tagger json rpc interface.
    The client only consists of the dispatcher with
    the server's request and notification signatures and
    still needs to be executed by a JsonRcpProtocol.
'''
from typing import List, Dict, Any
from stexls.trefier.models.tags import Tag
from stexls.util.jsonrpc import dispatcher
from stexls.util.jsonrpc.hooks import request
from stexls.util.jsonrpc import connection

__all__ = ['ClientDispatcher']


class ClientDispatcher(dispatcher.Dispatcher):
    ' Json-rpc client interface method. '
    @request
    def load_model(self, path: str, force: bool = False) -> Dict[str, Any]:
        ''' Loads a model and returns the model's information. '''

    @request
    def predict(self, *files: str) -> List[List[Tag]]:
        ' Creates a list of tags for each file provided in the argument. '

    @request
    def get_info(self) -> dict:
        ' Get info about loaded model. '

async def open_connection(host: str = 'localhost', port: int = 0):
    client, _ = await connection.open_connection(ClientDispatcher, host, port)
    return client

async def open_stdio_connection(fd_in = 'stdin', fd_out = 'stdout'):
    client, _ = await connection.open_stdio_connection(
        ClientDispatcher, fd_in, fd_out)
    return client