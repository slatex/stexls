''' This module implements the client side of the
    tagger json rpc interface.
    The client only consists of the dispatcher with
    the server's request and notification signatures and
    still needs to be executed by a JsonRcpProtocol.
'''
import asyncio
import logging
from typing import List
from stexls.trefier.models.tags import Tag
from stexls.util.cli import Cli, Arg, command
from stexls.util.jsonrpc import tcp
from stexls.util.jsonrpc import dispatcher
from stexls.util.jsonrpc.hooks import request, notification
from stexls.trefier.models.seq2seq import Seq2SeqModel

log = logging.getLogger(__name__)

__all__ = ['ClientDispatcher']


class ClientDispatcher(dispatcher.Dispatcher):
    ' Json-rpc client interface method. '
    @request
    def load_model(self, path: str, force: bool = False) -> dict:
        ''' Loads a model and returns the model's information. '''

    @request
    def predict(self, *files: str) -> List[List[Tag]]:
        ' Creates a list of tags for each file provided in the argument. '

    @request
    def get_info(self):
        ' Gets current server state. '
    
    @request
    def supported_prediction_types(self) -> List[str]:
        ' Gets list of supported prediction types. '
    
    @request
    def set_prediction_type(self, prediction_type: str) -> bool:
        ' Sets the remote models prediction type and returns success status. '
