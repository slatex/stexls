from typing import AsyncGenerator, Callable
import asyncio
import logging
import json
from .streams import MessageReaderStream
from .message import Message, Header, HeaderItem
from .. import core
from ..dispatcher import DispatcherBase, MessageTargetHandler

log = logging.getLogger(__name__)

__all__ = ['JsonRpcProtocol']

async def _read_input_stream(reader: asyncio.StreamReader, output: asyncio.Queue):
    message_reader = MessageReaderStream(
        reader,
        header=Header([
            HeaderItem('Content-Length', int, required=True),
            HeaderItem('Content-Type', str)]))
    try:
        while True:
            log.info('Waiting for message')
            message: Message = await message_reader.read()
            try:
                content = message.decode_content()
            except:
                log.exception('Failed to decode message content')
                continue
            await output.put(content)
    except EOFError:
        log.info('Reader stream closed')


async def _write_output_stream(writer: asyncio.StreamWriter, input: asyncio.Queue):
    try:
        while True:
            log.debug('Writer waiting for message to send.')
            message = await input.get()
            try:
                data = message.serialize()
            except ValueError:
                log.exception('Failed to serialize message.')
                continue
            log.info('Sending message (%i bytes)', len(data))
    except:
        writer.close()
        log.debug('Output stream writer closing')

class JsonRpcProtocolConnection(MessageTargetHandler):
    def __init__(self, peername: tuple):
        self.peername = peername

    async def receive(self, *message: core.Message):
        pass

class JsonRpcProtocol:
    def __init__(self, dispatcher_factory: Callable[[MessageTargetHandler], DispatcherBase]):
        self._connections = {}
        self.dispatcher_factory = dispatcher_factory
    
    async def on_connect(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        peername = writer.get_extra_info('peername')
        if peername in self._connections:
            raise ValueError(f'Peername already connected: {peername}')
        log.info('Connection established to %s', peername)
        input_queue = asyncio.Queue()
        output_queue = asyncio.Queue()
        target = JsonRpcProtocolConnection(peername)
        self._connections[peername] = self.dispatcher_factory(target)
        try:
            reader_task = _read_input_stream(reader, input_queue)
            writer_task = _write_output_stream(writer, output_queue)
            await asyncio.gather(reader_task, writer_task)
        finally:
            log.info('Closing connetion to %s', peername)
            del self._connections[peername]
            writer.close()

