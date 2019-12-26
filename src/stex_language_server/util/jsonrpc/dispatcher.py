from __future__ import annotations
from typing import Union, Any, Awaitable, Optional
from collections import defaultdict
import asyncio
import logging
import itertools
from .core import *
from .hooks import extract_methods
from .method_provider import MethodProvider

log = logging.getLogger(__name__)

__all__ = ['Dispatcher', 'DispatcherTarget']


class DispatcherTarget:
    ''' Represents a local version of the target of a dispatcher.
        The dispatcher generates a message and gives it to this
        fake "target". The "target" returns a future object for
        result of the sending operation. The true remote target
        then handles the dispatched message and returns
        some response to the fake local "target". The returned future
        object can now be resolved and the dispatcher receives
        the result.
        If the sent message does not expect some kind of result,
        None will be returned. '''
    async def dispatch(
        self, message: Union[MessageObject, List[MessageObject]]
        ) -> Optional[Union[MessageObject, List[MessageObject]]]:
        ' Makes the target dispatch a message and return a Awaitable response or None. '
        raise NotImplementedError()


class Dispatcher(MethodProvider):
    ''' A dispatcher is a hook that allows sending user messages to a connection
        between a client and the server.
        The dispatcher behaves like a normal python object, except that
        the called methods are done somewhere different and have to wait
        until the message is send, handled and the response returned.
    '''
    def __init__(self, target: DispatcherTarget = None):
        ' Initializes the dispatcher with a target for the messages it dispatches. '
        self.__target = target
        self.__request_id_generator = itertools.count(1)
        self.__methods = extract_methods(self)

    def is_method(self, method: str):
        ' Inherited. '
        return method in self.__methods
    
    async def call(self, method: str, params: Optional[Union[list, dict]] = None):
        ' Inherited. '
        function = self.__methods[method]
        log.debug('Resolved method %s: %s', method, function)
        if not params:
            log.debug('Calling %s without parameters.', method)
            result = function()
        elif isinstance(params, list):
            log.debug('Calling %s with args.', method)
            result = function(*params)
        elif isinstance(params, dict):
            log.debug('Calling %s with kwargs.', method)
            result = function(**params)
        else:
            raise TypeError(f'Invalid param type {type(params)}')
        if asyncio.iscoroutine(result):
            log.debug('Awaiting method result, then returning it.')
            return await result
        else:
            log.debug('Returning method result.')
            return result

    async def request(self, method: str, params: Union[list, dict, None] = None) -> Any:
        ' Sends a request message using the dispatch handler and awaits the results. '
        id = next(self.__request_id_generator)
        log.info('Dispatching request %s(%s) with id %i.', method, params, id)
        message = RequestObject(id, method, params)
        return await self.__target.dispatch(message)

    async def notification(self, method: str, params: Union[list, dict, None] = None):
        ' Sends a notification message using the dispatch handler and returns immediately. '
        log.info('Dispatching notification %s(%s).', method, params)
        message = NotificationObject(method, params)
        return await self.__target.dispatch(message)
