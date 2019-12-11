from __future__ import annotations
from typing import Union, Optional, Callable, List
from concurrent.futures import thread
import queue
import threading
import json
import socket
import socketserver
from stex_language_server.util.jsonrpc.core import *
from stex_language_server.util.jsonrpc.jsonrpc import *
from stex_language_server.util.promise import Promise
from stex_language_server.util.buffer import ByteBuffer

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

def read_jsonrpc_tcp_message(file):
    content_length = None
    for line in file:
        if not line:
            raise EOFError()
        parts = line.split()
        if len(parts) != 2:
            continue
        if parts[0].lower() != 'content-length:':
            continue
        if not parts[1].isdigit():
            continue
        content_length = int(parts[1])
    for line in file:
        if not line:
            raise EOFError()
        if line == '\n':
            break
    content = b''
    while len(content) < content_length:
        b = file.read(content_length - len(content))
        if not b:
            raise EOFError()
        content += b
    return content
        

class RpcTcpProtocol(socketserver.StreamRequestHandler):
    def __init__(self, dispatcher: JsonRpc, *args, **kwargs):
        super().__init__(*args, **kwargs)
        print("SET DISPATCHER", dispatcher)
        self.dispatcher = dispatcher

    def handle(self):
        print('connected', self.client_address, self.dispatcher)
        self.request.close()
        return
        msg = JsonRcpContentBuffer()
        buf = ByteBuffer()
        while True:
            buf.append(self.request.recv(1024))
            msg.append(buf)
            if not msg.is_ready():
                continue
            print('<--', msg.content)
            response = self.dispatcher.receive(msg.content)
            if isinstance(response, list):
                b = bytes('[' + ','.join(msg.serialize() for msg in response) + ']', 'utf-8')
            else:
                b = bytes(response.serialize(), 'utf-8')
            print('-->', b)
            self.request.sendall(b)
            msg.reset()
        print('exit', self.client_address)


class JsonRpcTcp(JsonRpc):
    def __init__(self):
        super().__init__()
    
    def server_forever(self,
        port: int = 0,
        host: str = 'localhost',
        backlog: int = 1):
        self.server = socketserver.TCPServer(
            (host, port), lambda *args, **kwrgs: RpcTcpProtocol(self, *args, **kwrgs))
        self.server.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        with self.server:
            self.host, self.port = self.server.socket.getsockname()
            print('created server', self.host, self.port)
            self.server.serve_forever()
    
    def send(self, message, target=None):
        print('server send', message, target)
        return
    
    def resolve(self, response):
        print('Server resolve', response)
        return
