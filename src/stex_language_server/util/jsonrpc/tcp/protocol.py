from typing import AsyncGenerator, Callable
import asyncio
import logging
import json
from collections import defaultdict
from .streams import MessageReaderStream, MessageWriterStream
from .message import Message, Header, HeaderItem
from ..dispatcher import DispatcherBase
from .. import core, util

log = logging.getLogger(__name__)

__all__ = ['JsonRpcProtocol']

async def _read_input_stream(
    reader: asyncio.StreamReader,
    incoming_messages: asyncio.Queue,
    outgoing_errors: asyncio.Queue):
    stream_reader = MessageReaderStream(
        reader,
        header=Header([
            HeaderItem('Content-Length', int, required=True),
            HeaderItem('Content-Type', str)]))
    log.info('Reader task started.')
    while True:
        log.debug('Waiting for message.')
        content: str = '<undefined>'
        try:
            content = await stream_reader.read()
            log.debug('Reader received content:\n\n%s', content)
            try:
                obj = json.loads(content)
            except json.JSONDecodeError:
                log.exception(content)
                await outgoing_errors.put(core.INVALID_REQUEST)
                continue
            invalid = util.validate_json(obj)
            if invalid is not None:
                log.warning('Invalid JSON (%s):\n\n%s', invalid.error.message, content)
                await outgoing_errors.put(invalid)
                continue
            jrpc_message = util.restore_message(obj)
            await incoming_messages.put(jrpc_message)
        except (EOFError, asyncio.CancelledError):
            log.info('Reader task finished.')
            await incoming_messages.put(None)
            await outgoing_errors.put(None)
            break
        except:
            log.exception('Failed to parse message:\n\n%s', content)
            await outgoing_errors.put(core.INVALID_REQUEST)

async def _write_output_stream(
    writer: asyncio.StreamWriter, outgoing_messages: asyncio.Queue):
    log.info('Writer task started.')
    stream_writer = MessageWriterStream(writer)
    try:
        while True:
            log.debug('Writer waiting for message to send.')
            message = await outgoing_messages.get()
            if message is None:
                break 
            log.debug('Writer writing message: %s', message)
            try:
                serialized = message.serialize()
            except:
                log.exception('Failed to serialize message.')
                continue
            try:
                stream_writer.write(serialized)
            except:
                log.exception('Failed to write serialized:\n\n%s', serialized)
                continue
    finally:
        log.info('Writer task finished.')
        writer.close()


class JsonRpcProtocol:
    def __init__(self, dispatcher: DispatcherBase):
        self._dispatcher = dispatcher
        self._connections = defaultdict(asyncio.Future)

    async def on_connect(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter):
        peername = writer.get_extra_info('peername')
        log.info('Protocol connected to %s.', peername)
        self._connections[peername].set_result(True)
        incoming_messages = asyncio.Queue()
        outgoing_messages = asyncio.Queue()
        try:
            receive_task = self._dispatcher.receive_task(peername, incoming_messages)
            send_task  = self._dispatcher.send_task(peername, outgoing_messages)
            reader_task = _read_input_stream(reader, incoming_messages, outgoing_messages)
            writer_task = _write_output_stream(writer, outgoing_messages)
            await asyncio.gather(
                receive_task,
                send_task,
                reader_task,
                writer_task)
            log.info('Protocol receive, send read and write tasks exited.')
        finally:
            writer.close()
            del self._connections[peername]
            log.info('Closing connection to %s.', peername)
