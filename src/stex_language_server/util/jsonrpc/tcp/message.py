from __future__ import annotations
from typing import List, Any
import logging
import re

log = logging.getLogger(__name__)

class HeaderItem:
    def __init__(self, name: str, value_type: type, required: bool = False):
        self.name = name
        self.value_type = value_type
        self.required = required
        self.value = None
    
    def copy(self) -> HeaderItem:
        item = HeaderItem(
            name=self.name,
            value_type=self.value_type,
            required=self.required)
        item.value = self.value
        log.debug('Copying header item "%s: %s"', item.name, item.value)
        return item

    def serialize(self, encoding: str = 'utf-8') -> bytes:
        return bytes(f'{self.name}: {self.value}', encoding)


class Header:
    def __init__(self, header_items: List[HeaderItem] = None, copy: bool = False):
        self.header_items = {
            item.name.lower(): item.copy() if copy else item
            for item in header_items or ()
        }
    
    def copy(self) -> Header:
        return Header(self.header_items.values(), copy=True)
    
    def reset(self):
        for item in self.header_items.values():
            item.value = None

    def ready(self) -> bool:
        return all(
            not item.required or item.value is not None
            for item in self.header_items.values())
    
    def add_line(self, line: str):
        try:
            name, value = line.split(':')
        except:
            raise ValueError(f'Line does not consist of a name and value pair: {line}')
        name = name.strip()
        value = value.strip()
        if name.lower() not in self.header_items:
            log.debug('Ignoring header option "%s"', name)
        else:
            log.debug('Setting header option "%s" to "%s"', name, value)
            self.set_value(name.lower(), value)
    
    def get_value(self, name: str) -> Any:
        item = self.header_items.get(name.lower())
        if item is None:
            return None
        return item.value
    
    def set_value(self, name: str, value: Any):
        item = self.header_items.get(name.lower())
        if item is None:
            raise ValueError(f'Item "{name}" does not exist.')
        item.value = item.value_type(value)
    
    def serialize(self, encoding: str = 'utf-8', linebreak: str = '\r\n') -> bytes:
        if not self.ready():
            log.error('Attempting to serialize invalid header')
            raise ValueError('Header not ready to be serialized.')
        log.debug('Serializing header (%i items).', len(self.header_items))
        for item in self.header_items.values():
            log.debug('HeaderItem: %s=%s', item.name, item.value)
        s = linebreak.join(
            f'{item.name}: {item.value}'
            for item in self.header_items.values()
            if item.value is not None)
        return bytes(s + linebreak + linebreak, encoding)


class Message:
    _EXTRACT_CHARSET_RE = re.compile(r'''(?<!\w)charset=([\w\-]+)''')

    def __init__(self, header: Header, content: bytes):
        self.content = content
        self.header = header
    
    def decode_content(self) -> str:
        charset = 'utf-8'
        content_type = self.header.get_value('content-type')
        if content_type is not None:
            for match in Message._EXTRACT_CHARSET_RE.finditer(content_type):
                charset = match.group(1)
                break
        log.debug('Decoding content as "%s"', charset)
        return self.content.decode(charset)

    def serialize(self, header_encoding: str = 'utf-8', linebreak: str = '\r\n') -> bytes:
        actual_length = len(self.content)
        content_length = self.header.get_value('content-length')
        if actual_length != content_length:
            raise ValueError(
                f'Header content-length ({content_length}) '
                f'and actual content length ({actual_length}) do not match.')
        header = self.header.serialize(encoding=header_encoding, linebreak=linebreak)
        return header + self.content

__all__ = ['Message', 'Header', 'HeaderItem']
