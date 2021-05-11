from __future__ import annotations

import asyncio
import inspect
import json
import logging
from stexls.jsonrpc.exceptions import JsonRpcException
from typing import Any, Awaitable, Callable, List, Optional, Union, Dict

from .core import (ErrorCodes, ErrorObject, MessageObject, NotificationObject, RequestObject,
                   ResponseObject)
from .parser import MessageParser
from .streams import JsonStream

log = logging.getLogger(__name__)

__all__ = ['JsonRpcConnection']


class JsonRpcConnection:
    ' This is a implementation for the json-rpc-protocol. '

    def __init__(self, stream: JsonStream):
        """ Initializes the connection with a stream which can read and write json data.

        Args:
            stream: IO Stream which handles json serialization and protocol header stuff.
        """
        self._stream = stream
        self._methods: Dict[str, Callable] = {}
        self._requests: Dict[Union[str, int], asyncio.Future] = {}

    def close(self):
        """ Closes the underlaying stream. """
        self._stream.close()

    def on(self, method: str, callback: Callable):
        """ Registers a method as a request and notification handler.

        Args:
            method (str): Method name to register.
            callback (Callable): The function body that will be called.
        """
        if method in self._methods:
            raise ValueError(
                f'Method "{method}" is already registered with this protocol.')
        self._methods[method] = callback

    def send(self, message: Union[NotificationObject, RequestObject]) -> Optional[Awaitable[Any]]:
        """ Sends a message of any type.

        Args:
            message: A message you want to send.

        Returns:
            Optional[Awaitable[Any]]: A future with the result of a request.
        """
        if isinstance(message, NotificationObject):
            self.send_notification(message)
        elif isinstance(message, ResponseObject):
            raise ValueError('The user should not send response objects.')
        elif isinstance(message, RequestObject):
            return self.send_request(message)
        return None

    def send_notification(self, message: NotificationObject):
        ' Specifically sends a notification. '
        self._stream.write_json(message)

    def send_request(self, message: RequestObject) -> Awaitable[Any]:
        ' Sends a request and returns the future object with the results. '
        if message.id in self._requests:
            raise ValueError('Duplicate message id.')
        result: asyncio.Future = asyncio.Future()
        self._requests[message.id] = result
        self._stream.write_json(message)
        return result

    def _handle_response(self, response: ResponseObject):
        ''' Handles an response object.

        Performs error checks and resolves request if ids match.
        '''
        if response.id is None:
            log.warning('Received response without id:\n%s', response)
        elif response.id not in self._requests:
            log.warning('Received response with unknown id:\n%s', response)
        else:
            log.debug('Resolving request:\n%s', response)
            result = self._requests[response.id]
            del self._requests[response.id]
            if hasattr(response, 'error'):
                result.set_exception(response.error.to_exception())
            else:
                result.set_result(response.result)

    async def _handle_notification(self, notification: NotificationObject):
        ' Handles incoming notifications. This only calls the contained method. '
        await self.call(
            notification.method, getattr(notification, 'params', None))

    async def _handle_request(self, request: RequestObject) -> Any:
        """ Handles a request.

        Calls the contained method with parameters and returns the response object.

        Returns:
            ResponseObject: ResponseObject with results or errors.
        """
        return await self.call(
            request.method, getattr(request, 'params', None), request.id)

    async def _handle_message(
            self, message: MessageObject) -> Optional[ResponseObject]:
        " Handles any type of incoming message and returns the response if it is a request. "
        if isinstance(message, ResponseObject):
            self._handle_response(message)
        elif isinstance(message, NotificationObject):
            await self._handle_notification(message)
        elif isinstance(message, RequestObject):
            return await self._handle_request(message)
        return None

    async def call(
            self,
            method: str,
            params: Union[List, dict, None] = None,
            id: Union[int, str] = None) -> Optional[ResponseObject]:
        """ Calls a registered method.

        Searches for the specified method and executes it using the list or dict
        of parameters. If an ID is given, an response will be returned with the
        execution results.

        Args:
            method: Method to execute.
            params: Optional parameters passed to the method.
            id: Optional response id. Responses will only be generated if this is not None.

        Returns:
            Optional[ResponseObject]: Response object with the given ID if given.
        """
        if method not in self._methods:
            log.warning('Method "%s" not found.', method, exc_info=True)
            response = ResponseObject(
                id, error=ErrorObject(ErrorCodes.MethodNotFound, data=method))
        else:
            try:
                m = self._methods[method]
                if params is None:
                    result = m()
                elif isinstance(params, list):
                    for i, (value, (name, param)) in enumerate(zip(params, inspect.signature(m).parameters.items())):
                        if hasattr(param.annotation, 'from_json') and callable(param.annotation.from_json):
                            log.debug(
                                f'Found callable "from_json" in type "{param.annotation}" of param {name}.')
                            try:
                                params[i] = param.annotation.from_json(value)
                            except Exception:
                                log.exception(
                                    f'Failed to deserialize param "{name}" in method call "{method}"')
                    result = m(*params)
                elif isinstance(params, dict):
                    for name, param in inspect.signature(m).parameters.items():
                        if name in params and hasattr(param.annotation, 'from_json') and callable(param.annotation.from_json):
                            log.debug(
                                f'Found callable "from_json" in type "{param.annotation}" of param {name}.')
                            try:
                                params[name] = param.annotation.from_json(
                                    params[name])
                            except Exception:
                                log.exception(
                                    f'Failed to deserialize param "{name}" in method call "{method}"')
                    result = m(**params)
                else:
                    raise ValueError(
                        f'Expected params of type dict or list, found: {type(params)}')
                log.debug('Method %s(%s) call successful.', method, params)
                if asyncio.iscoroutine(result):
                    log.debug(f'Called method "{method}" returned coroutine.')
                    result = await result
                response = ResponseObject(id, result=result)
            except TypeError as e:
                log.warning(
                    'Method %s(%s) threw possible InvalidParams error.', method, params, exc_info=True)
                response = ResponseObject(
                    id, error=ErrorObject(ErrorCodes.InvalidParams, message=str(e)))
            except JsonRpcException as e:
                log.exception(
                    'Method %s(%s) raised an json rpc specific exception.', method, params)
                response = ResponseObject(
                    id, error=ErrorObject(code=int(e), message=str(e), data=e.data))
            except Exception as e:
                log.exception(
                    'Method %s(%s) raised an unexpected error.', method, params)
                response = ResponseObject(
                    id, error=ErrorObject(ErrorCodes.InternalError, message=str(e)))
        return response

    async def _handle(self, obj: dict):
        """ Handles an incoming raw message.

        The input is parsed as a MessageObject or batch of message objects.
        the parsed messages are handled in parallel
        and responses and errors are written to the output stream.

        Args:
            obj: Some dictionary parsed using json.
        """
        parser = MessageParser(obj)
        log.debug(
            "Parsed message (%i valid, %i errors).", len(parser.valid), len(parser.errors))
        responses = await asyncio.gather(
            *map(self._handle_message, parser.valid))
        filtered_responses: List[ResponseObject] = list(
            filter(None, responses))
        responses_and_errors = filtered_responses + parser.errors
        if not responses_and_errors:
            log.debug('No response to send back.')
        elif parser.is_batch:
            self._stream.write_json(responses_and_errors)
        else:
            for response in responses_and_errors:
                self._stream.write_json(response)

    async def run_forever(self):
        ' Launches the incoming message reader. '
        log.info('Reader task started.')
        try:
            while True:
                log.debug('Waiting for message from stream.')
                try:
                    obj = await self._stream.read_json()
                    log.debug('Message received: %s', obj)
                    asyncio.create_task(self._handle(obj))
                except json.JSONDecodeError as e:
                    log.exception(
                        'Reader encountered exception while parsing json.')
                    response = ResponseObject(None, error=ErrorObject(
                        ErrorCodes.ParseError, message=str(e)))
                    self._stream.write_json(response)
        except (EOFError, asyncio.CancelledError, asyncio.IncompleteReadError) as e:
            log.debug('Connection task closing because of exception: %s', type(e))
            self._stream.close()
        finally:
            log.info('Connection task closed.')
