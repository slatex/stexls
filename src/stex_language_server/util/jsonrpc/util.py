from typing import Tuple, List, Iterator
import json
from ..buffer import ByteBuffer
from .core import RequestMessage, NotificationMessage, ResponseMessage, Message, PARSE_ERROR, INVALID_REQUEST


def json2message(obj: dict) -> Message:
    ''' Parses the json object and attemps to restore the original Message object.
    Returns:
        Returns the original message object or raises a ValueError
        if the json object is invalid.
    '''
    if not isinstance(obj, dict):
        raise ValueError('Object must be an object.')
    protocol = obj.get('jsonrpc')
    if protocol is None or protocol != '2.0':
        raise ValueError(f'Invalid protocol: {protocol}')
    if 'method' in obj and 'id' in obj and obj['id'] is None:
        raise ValueError('Request object must not have id "null".')
    if 'params' in obj and obj['params'] is None:
        raise ValueError('"params" must not be null.')
    if 'result' in obj and 'error' in obj:
        raise ValueError('"result" and "error" must not be present at the same time.')
    if 'error' in obj and obj['error'] is None:
        raise ValueError('"error" must not be null.')
    if 'result' in obj and obj['result'] is None:
        raise ValueError('"result" must not be null.')
    if 'method' in obj:
        if 'id' in obj:
            return RequestMessage(obj['id'], obj['method'], obj.get('params'))
        else:
            return NotificationMessage(obj['method'], obj.get('params'))
    elif 'result' in obj:
        return ResponseMessage(obj.get('id'), result=obj['result'])
    elif 'error' in obj:
        return ResponseMessage(obj.get('id'), error=obj['error'])
    else:
        raise ValueError('Unable to restore message.')


def parse(raw: str) -> Tuple[List[Message], bool, List[Message]]:
    ''' Parses the raw string as a json object.
    Parameters:
        raw: A json desirializable string.
    Return:
        3-Tuple of
        [0] Messages that need to be handled.
        [1] If these messages are to be handled as a batch.
        [2] Messages that do not need to be handled before being returned.
    '''
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        return [], False, [PARSE_ERROR]
    if isinstance(obj, dict):
        try:
            return [json2message(obj)], False, []
        except ValueError:
            return [], False, [INVALID_REQUEST]
    elif isinstance(obj, list):
        batch = []
        errors = []
        for o in obj:
            try:
                batch.append(json2message(o))
            except ValueError:
                errors.append(INVALID_REQUEST)
        return batch, True, errors
    return [], False, [INVALID_REQUEST]


class JsonRcpContentBuffer:
    ' Buffers the content of a json rcp message over tcp. '
    def __init__(self):
        self.reset()
        self.byte_buffer = ByteBuffer()
    
    def reset(self):
        ' Clears state and makes it possible to receive a new message. '
        self.content_length = None
        self.header_received = False
        self.content = b''
    
    def is_ready(self) -> bool:
        ' Returns true if a header was received and the content-length = len(content)'
        return self.header_received and len(self.content) == self.content_length

    def append(self, data: bytes, with_header: bool = False) -> Iterator[bytes]:
        ' Appends data to the internal buffer and '
        if not data:
            raise ValueError('Appending zero bytes is probably a mistake.')
        self.byte_buffer.append(data)
        while True:
            while self.content_length is None and self.byte_buffer.has_line():
                line = self.byte_buffer.readln()
                parts = line.split()
                if len(parts) != 2: continue
                if parts[0] != 'content-length:': continue
                if not parts[1].isdigit(): continue
                self.content_length = int(parts[1])
            while not self.header_received and self.byte_buffer.has_line():
                self.header_received = not self.byte_buffer.readln()
            while (self.header_received
                    and len(self.content) < self.content_length):
                missing_count = self.content_length - len(self.content)
                if not self.byte_buffer.size() >= missing_count:
                    break
                self.content += self.byte_buffer.readbytes(missing_count)
            if self.is_ready():
                if with_header:
                    yield self.content, bytes(f'content-length: {self.content_length}\n\n', 'utf-8')
                else:
                    yield self.content
                self.reset()
            else:
                break
