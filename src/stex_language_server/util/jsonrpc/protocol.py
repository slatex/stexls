from __future__ import annotations
from typing import Iterable, Callable, Iterator, Tuple, Union
import asyncio
import logging
import itertools
import json
from .core import *
from .util import restore_message, validate_json

log = logging.getLogger(__name__)

__all__ = [
    'JsonRpcProtocol',
    'JsonRpcMessage',
    'ReaderStream',
    'WriterStream',
    'MessageHandler',
    'InputHandler'
]

class JsonRpcMessage:
    ''' This class represents a message in transit.
        A message can be a list of jrpc objects,
        but it also can just be a single jrpc object.
        The message can be built by adding requests,
        notifications an responses. After that it
        can be serialized using to_json and sent
        using any transmissin protocol.
        The target can then deserialize the message
        using from_json. All requests, notifications and responses
        in the given string will be placed accordingly and erros,
        if any occured during deserialization,
        can be queried using the errors() getter.
    '''
    def __init__(self, objects: Iterable[MessageObject] = (), is_batch: bool = False, errors: Iterable[ResponseObject] = ()):
        ' Initializes the message by storing the given objects. '
        self._requests = tuple(
            o for o in objects if isinstance(o, RequestObject))
        self._notifications = tuple(
            o for o in objects if isinstance(o, NotificationObject))
        self._responses = tuple(
            o for o in objects if isinstance(o, ResponseObject))
        self._errors = tuple(errors)
        self._is_batch = is_batch

    def requests(self) -> Iterable[RequestObject]:
        ' Iterable of requests in this message. '
        return self._requests

    def notifications(self) -> Iterable[NotificationObject]:
        ' Iterable of notifications in this message. '
        return self._notifications

    def responses(self) -> Iterable[ResponseObject]:
        ' Iterable of responses in this message. '
        return self._responses
    
    def objects(self) -> Iterator[MessageObject]:
        ' Iterator with all types of messages in this object. '
        return itertools.chain(
            self.requests(), self.notifications(), self.responses())

    def errors(self) -> Iterable[ResponseObject]:
        ''' List of errors that occured or were detected while parsing this message. 
            These errors must be send back to the origin. '''
        return self._errors

    def is_batch(self) -> bool:
        ' Gets the internal flag of whether the objects form a single batch or not. '
        return self._is_batch

    @staticmethod
    def from_json(string: str) -> JsonRpcMessage:
        ' Deserializes the json string. '
        log.info('Deserializing message from json. (%i characters)', len(string))
        try:
            message = json.loads(string)
        except json.JSONDecodeError as e:
            log.exception('Failed to parse json:\n\n%s', string)
            err = ResponseObject(None, error=ErrorObject(ErrorCodes.InvalidRequest, data=str(e)))
            return JsonRpcMessage(errors=(err,))
        if not isinstance(message, (dict, list)):
            log.warning('Deserialized json string must be a list or dictionary. Found: %s\n\n%s', type(message), message)
            err = ResponseObject(None, error=ErrorObject(ErrorCodes.InvalidRequest))
            return JsonRpcMessage(errors=(err,))
        if isinstance(message, dict):
            invalid = validate_json(message)
            if invalid is not None:
                log.warning('Object failed validation: %s', message)
                return JsonRpcMessage(errors=(invalid,))
            restored = restore_message(message)
            log.debug('Restored single message: %s', restored)
            return JsonRpcMessage(objects=(restored,))
        elif isinstance(message, list):
            log.debug('Restoring batch (%i entries).', len(message))
            errors = []
            objects = []
            for msg in message:
                invalid = validate_json(msg)
                if invalid is not None:
                    log.warning('Batch entry failed validation: %s', msg)
                    errors.append(invalid)
                else:
                    restored = restore_message(msg)
                    log.debug('Restored batch entry: %s', restored)
                    objects.append(restored)
            log.debug('Batch restored %i objects (%i errors).', len(objects), len(errors))
            return JsonRpcMessage(
                objects=objects, is_batch=True, errors=errors)

    def to_json(self) -> Iterator[str]:
        ''' Serializes all messages as json strings and yields
            the serialized strings for every message.
            If is_batch() is True, yields a single string with an
            json array that contains all serialized messages. '''
        serializations = tuple(
            json.dumps(obj, default=lambda x: x.__dict__)
            for obj in self.objects())
        log.debug('Serialized messages: %a', serializations)
        if self.is_batch():
            serialized = '[' + ','.join(serializations) + ']'
            yield serialized
        else:
            yield from serializations

    def __repr__(self):
        return (
            '[JsonRpcMessage objects=['
            + ','.join(map(str, self.objects()))
            + '] errors=['
            + ','.join(map(str, self.errors()))
            + f'] is_batch={self.is_batch()}]')


class ReaderStream:
    ''' A reader stream parses incoming bytestreams or packages
        of serialized json rpc objects,
        deserialzies them and returns them as a JsonRpcMessage.
    '''
    async def read(self) -> Optional[JsonRpcMessage]:
        ''' Reads a jsonrpc message from the stream.
        Returns:
            JsonRpcMessage or None if there will be no more messages.
        '''
        raise NotImplementedError()


class WriterStream:
    ''' A writer stream takes a JsonRpcMessage and
        serializes the contained objects and sends them back.
    '''
    async def write(self, message: JsonRpcMessage):
        ' Serializes and writes a message to the stream. '
        raise NotImplementedError()


class MessageHandler:
    ''' A message handler provides the services needed to
        handle request, notification and response objects.
    '''
    async def handle_request(self, request: RequestObject) -> ResponseObject:
        ' Executes a request method and returns the response object. '
        raise NotImplementedError()

    async def handle_notification(self, notification: NotificationObject):
        ' Executes a notification method and returns. '
        raise NotImplementedError()

    async def handle_response(self, response: ResponseObject):
        ' Resolves the request object with the same id as the response object. '
        raise NotImplementedError()


class InputHandler:
    ' This represents input done by the user and not by the protocol. '
    async def get_user_input(self) -> JsonRpcMessage:
        ''' Creates a future that resolves to a json rpc message made by the user.
        Returns:
            JsonRpcMessage or None if no more message will be sent this way.
        '''
        raise NotImplementedError()


class Inspector:
    ''' An interface for an server inspector.
        Provides methods that allow for inspection of incoming and outgoing messages.
    '''
    def __init__(self):
        self._queue = asyncio.Queue()
    
    def add_outgoing(self, message: MessageObject):
        ' Adds a message to the outgoing queue. '
        self._queue.put_nowait(('outgoing', message))
    
    def add_incoming(self, message: MessageObject):
        ' Adds a message to the incoming queue. '
        self._queue.put_nowait(('incoming', message))
    
    async def get(self) -> Tuple[Union['incoming', 'outgoing'], MessageObject]:
        ''' Gets the next message sent or received.
        Returns:
            2-Tuple of ('incoming' | 'outgoing', MessageObject)
            or None if there will be no more outgoing messages.
        '''
        log.debug('Inspector waiting for a new message to inspect.')
        return await self._queue.get()
    
    def close(self):
        log.debug('Closing inspector.')
        self._queue.put_nowait(None)
        self._queue = None


class JsonRpcProtocol:
    ' This is a implementation for the json-rpc-protocol. '
    def __init__(
        self,
        user_input_handler: InputHandler,
        message_handler: MessageHandler,
        reader: ReaderStream,
        writer: WriterStream):
        ''' Initializes the protocol.
        Parameters:
            user_input_handler: An interface which allows to listen
                for messages generated locally by the user.
            message:handler: An interface with functions that
                can execute Requests and Notifications and can resolve
                requests.
            reader: An interface to a stream which allows parsing the
                data received into useful JsonRpcMessages.
            writer: An interface to a stream which allows sending
                JsonRpcMessage by taking care of the serialization process
                and writing it some kind of connection.
        '''
        self.__user_input_handler = user_input_handler
        self.__message_handler = message_handler
        self.__reader = reader
        self.__writer = writer
        self.__writer_queue = asyncio.Queue()
        self.__inspectors: List[Inspector] = []

    def make_inspector(self) -> Inspector:
        ' Adds an inspector to this protocol. '
        inspector = Inspector()
        self.__inspectors.append(inspector)
        log.debug('Adding inspector to protocol (%i inspectors).', len(self.__inspectors))
        return inspector
    
    def remove_inspector(self, inspector: Inspector):
        ' Removes an inspector from this protocol. '
        self.__inspectors.remove(inspector)

    async def close(self):
        log.info('JsonRpcProtocol close() called.')
        await self.__writer_queue.put(None)
        for i in self.__inspectors:
            await i.close()
    
    async def _handle_message(self, message: JsonRpcMessage) -> JsonRpcMessage:
        ''' Handles all message objects in a json rpc message.
        Returns:
            A json rpc message with the response objects to the inputs.
        '''
        log.info('Handling message %s.', message)
        request_tasks = list(map(
            asyncio.create_task,
            map(self.__message_handler.handle_request, message.requests())))
        tasks = map(
            asyncio.create_task,
            itertools.chain(
                map(self.__message_handler.handle_notification, message.notifications()),
                map(self.__message_handler.handle_response, message.responses())))
        await asyncio.gather(*tasks)
        responses = [
            await response
            for response in request_tasks]
        responses.extend(message.errors())
        log.debug('Message handled and generated %s responses.', len(responses))
        return JsonRpcMessage(responses, is_batch=message.is_batch())
    
    async def _reader_task(self):
        ''' The reader tasks listens to to the internal ReaderStream
            and waits for messages sent over the connection.
            The received message is handled according to it's type
            and the responses are forwared to the writer task. '''
        log.info('Reader task started.')
        try:
            while True:
                log.debug('Waiting for message from stream.')
                message: JsonRpcMessage = await self.__reader.read()
                log.debug('Message received: %s', message)
                if message is None:
                    log.info('Message terminator received.')
                    break
                for inspector in self.__inspectors:
                    log.debug('Adding incoming messages to inspector %s.', inspector)
                    for msg in message.objects():
                        inspector.add_incoming(msg)
                responses = await self._handle_message(message)
                log.debug('Sending responses to the writer task: %s', responses)
                await self.__writer_queue.put(responses)
        except (EOFError, asyncio.CancelledError) as e:
            log.info('Reader task exiting because of %s.', type(e))
        finally:
            await self.close()
        log.info('Reader task finished.')
    
    async def _writer_task(self):
        ''' The writer tasks waits for messages that need to be sent to
            the protocol's target. When a message is received,
            it is handled by the internal WriterStream. '''
        log.info('Writer task started.')
        try:
            while True:
                log.debug('Writer waiting for message from queue.')
                message: JsonRpcMessage = await self.__writer_queue.get()
                log.debug('Message received: %s', message)
                if message is None:
                    log.debug('Writer task terminator received.')
                    break
                for inspector in self.__inspectors:
                    log.debug('Adding outgoing messages to inspector %s.', inspector)
                    for msg in message.objects():
                        inspector.add_outgoing(msg)
                log.debug('Writing message to stream.')
                await self.__writer.write(message)
        except asyncio.CancelledError:
            log.debug('Writer task stopped because of cancellation event.')
        log.info('Writer task finished.')
    
    async def _user_input_task(self):
        ''' Runs the user input task, which waits for user made messages
            and forwards them to the writer tasks in order to send them to the
            client or server.
        '''
        log.info('User input task started.')
        try:
            while True:
                log.debug('Waiting for user input.')
                message: JsonRpcMessage = await self.__user_input_handler.get_user_input()
                log.debug('User message received: %s', message)
                if message is None:
                    log.debug('User task terminator received.')
                    break
                log.debug('Forwarding user input to writer task.')
                await self.__writer_queue.put(message)
        except asyncio.CancelledError:
            log.debug('User input task stopping due to cancellation event.')
        log.info('User input task finished.')
    
    async def run_until_finished(self):
        ' Runs the protocol until all subtasks finish. '
        log.info('JsonRpcProtocol starting.')
        await asyncio.gather(
            self._user_input_task(),
            self._reader_task(),
            self._writer_task())
        log.info('JsonRpcProtocol all tasks finished. Exiting.')
