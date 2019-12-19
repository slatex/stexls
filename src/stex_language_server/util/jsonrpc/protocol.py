from typing import Iterable, Callable
import asyncio
import logging
from .core import *

log = logging.getLogger(__name__)

class JsonRpcMessage:
    ''' This class represents a message.
        A message can be a list of jrpc objects,
        but it also can just be a single jrpc object.
    '''
    def requests(self) -> Iterable[RequestObject]:
        ' Iterable of requests in this message. '
        raise NotImplementedError()

    def notifications(self) -> Iterable[NotificationObject]:
        ' Iterable of notifications in this message. '
        raise NotImplementedError()

    def responses(self) -> Iterable[ResponseObject]:
        ' Iterable of responses in this message. '
        raise NotImplementedError()

    def set_responses(self, responses: Iterable[ResponseObject]):
        ' Sets the output of self.responses(). '
        raise NotImplementedError()

    def errors(self) -> Iterable[ResponseObject]:
        ''' List of errors that occured or were detected while parsing this message. 
            These errors must be send back to the origin. '''
        raise NotImplementedError()

    def set_batch(self, value: bool):
        ' Sets the internal flag for whether the objects in this message should be transported as a batch. '
        raise NotImplementedError()

    def is_batch(self) -> bool:
        ' Gets the internal flag of whether the objects form a single batch or not. '
        raise NotImplementedError()


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
    async def request(self, request: RequestObject) -> ResponseObject:
        ' Executes a request method and returns the response object. '
        raise NotImplementedError()

    async def notification(self, notification: NotificationObject):
        ' Executes a notification method and returns. '
        raise NotImplementedError()

    async def response(self, response: ResponseObject):
        ' Resolves the request object with the same id as the response object. '
        raise NotImplementedError()


class InputHandler:
    ' This represents input done by the user and not by the protocol. '
    async def get(self) -> JsonRpcMessage:
        ''' Creates a future that resolves to a json rpc message made by the user.
        Returns:
            JsonRpcMessage or None if no more message will be sent this way.
        '''
        raise NotImplementedError()


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
    
    async def _handle_message(self, message: JsonRpcMessage) -> JsonRpcMessage:
        ''' Handles all message objects in a json rpc message.
        Returns:
            A json rpc message with the response objects to the inputs.
        '''
        log.info('Handling message %s.', message)
        responses = list(message.errors())
        for request in message.requests():
            log.debug('Handle request: %s', request)
            response = await self.__message_handler.request(request)
            responses.append(response)
        for notification in message.notifications():
            log.debug('Handle notification: %s', notification)
            await self.__message_handler.notification(notification)
        for response in message.responses():
            log.debug('Handle response: %s', response)
            await self.__message_handler.response(response)
        out = JsonRpcMessage()
        out.set_batch(message.is_batch())
        log.debug('Message handled and generated %s responses.', len(responses))
        out.set_responses(responses)
        return out
    
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
                responses = await self._handle_message(message)
                log.debug('Sending %s responses to the writer task.', len(responses))
                await self.__writer_queue.put(responses)
        except (EOFError, asyncio.CancelledError) as e:
            log.info('Reader task exiting because of %s.', type(e))
        finally:
            log.debug('Putting terminator in writer queue.')
            await self.__writer_queue.put(None)
        log.info('Reader task finished.')
    
    async def _writer_task(self):
        ''' The writer tasks waits for messages that need to be sent to
            the protocol's target. When a message is received,
            it is handled by the internal WriterStream. '''
        log.info('Writer task started.')
        try:
            while True:
                log.debug('Writer waiting for message from queue.')
                message: JsonRpcMessage = self.__writer_queue.get()
                log.debug('Message received: %s', message)
                if message is None:
                    log.debug('Writer task terminator received.')
                    break
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
                message: JsonRpcMessage = await self.__user_input_handler.get()
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
