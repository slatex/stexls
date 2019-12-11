from ..buffer import ByteBuffer
from .core import RequestMessage, NotificationMessage, ResponseMessage, Message

def json2message(obj: object) -> Message:
    ''' Parses the json object and attemps to restore the original Message object.
    Returns:
        Returns the original message object or raises a ValueError
        if the json object is invalid.
    '''
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


class JsonRcpContentBuffer:
    def __init__(self):
        self.reset()
    
    def reset(self):
        self.content_length = None
        self.header_received = False
        self.content = b''
    
    def is_ready(self) -> bool:
        return self.header_received and len(self.content) >= self.content_length
    
    def append(self, data: ByteBuffer):
        if self.is_ready():
            raise ValueError('Message already received: Unable to append more data.')
        while self.content_length is None and data.has_line():
            line = data.readln()
            parts = line.split()
            if len(parts) != 2: continue
            if parts[0] != 'content-length:': continue
            if not parts[1].isdigit(): continue
            self.content_length = int(parts[1])
        while not self.header_received and data.has_line():
            self.header_received = not data.readln()
        while (self.header_received
                and len(self.content) < self.content_length):
            missing_count = self.content_length - len(self.content)
            if not data.size() >= missing_count:
                break
            self.content += data.readbytes(missing_count)
        return self.is_ready()
