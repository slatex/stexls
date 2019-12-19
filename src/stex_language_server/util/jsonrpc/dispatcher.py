from __future__ import annotations
from typing import Union, Any, Awaitable, Optional
from collections import defaultdict
import asyncio
import logging
import itertools
from .core import *
from .hooks import extract_methods

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
    async def dispatch(self, message: MessageObject) -> Optional[Awaitable[ResponseObject]]:
        ' Makes the target dispatch a message and return a Awaitable response or None. '
        raise NotImplementedError()


class Dispatcher:
    ''' A dispatcher is a hook that allows sending user messages to a connection
        between a client and the server.
        The dispatcher behaves like a normal python object, except that
        the called methods are done somewhere different and have to wait
        until the message is send, handled and the response returned.
    '''
    def __init__(self, target: DispatcherTarget):
        ' Initializes the dispatcher with a target for the messages it dispatches. '
        self.__target = target
        self.__methods = extract_methods(self)
        self.__id_generator = itertools.count(1)
        self.__requests = defaultdict(asyncio.Future)
        self.__targets = defaultdict(asyncio.Queue)
        self.__default_target = asyncio.Future()

    async def request(self, method: str, params: Union[list, dict, None] = None) -> Any:
        ' Sends a request message using the dispatch handler and awaits the results. '
        id = next(self.__id_generator)
        log.info('Dispatching request %s(%s) with id %i.', method, params, id)
        message = RequestObject(id, method, params)
        return await self.__target.dispatch(message)

    async def notification(self, method: str, params: Union[list, dict, None] = None):
        ' Sends a notification message using the dispatch handler and returns immediatly. '
        log.info('Dispatching notification %s(%s).', method, params)
        message = NotificationObject(method, params)
        return await self.__target.dispatch(message)

    async def call(
        self,
        method: str,
        params: Union[list, dict, None],
        id: Union[int, str] = None) -> Optional[ResponseObject]:
        ' Calls the given method with the parameters and generates a response object according to the results. '
        log.info('Method %s(%s) called with id %s.', method, params, id)
        fn = self.__methods.get(method)
        if not fn:
            log.warning('Method %s not found.', method)
            response = ResponseObject(
                id, error=ErrorObject(ErrorCodes.MethodNotFound, data=method))
        else:
            try:
                if params is None:
                    result = fn()
                elif isinstance(params, list):
                    result = fn(*params)
                elif isinstance(params, dict):
                    result = fn(**params)
                else:
                    raise TypeError(f'Invalid params type: {type(params)}')
                if asyncio.iscoroutine(result):
                    log.debug('Called method %s returned an coroutine object.', method)
                    result = await result
                log.debug('Method %s(%s) called successfully.', method, params)
                response = ResponseObject(
                    id, result=result)
            except TypeError as e:
                log.exception('Method %s(%s) threw possible InvalidParams error.', method, params)
                response = ResponseObject(
                    id, error=ErrorObject(ErrorCodes.InvalidParams, data=str(e)))
            except Exception as e:
                log.exception('Method %s(%s) threw an unknown error.', method, params)
                response = ResponseObject(
                    id, error=ErrorObject(ErrorCodes.InternalError, data=str(e)))
        if id is not None:
            log.debug('Returning response to method call of %s(%s) with id %s.', method, params, id)
            return response
