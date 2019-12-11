from __future__ import annotations
from typing import Union, Optional, List, Dict, Any
import socket
import socketserver
from .core import *
from .jsonrpc import JsonRpc
from .util import JsonRcpContentBuffer
from ..buffer import ByteBuffer

class JsonRpcHandler(socketserver.BaseRequestHandler):
    def handle(self):
        print('connected', self.client_address)
        dispatcher: JsonRpc = self.server.dispatcher
        buffer = ByteBuffer()
        message_buffer = JsonRcpContentBuffer()
        wfile = self.request.makefile('wb')
        try:
            while True:
                print("ENTER LOOP")
                data = self.request.recv(1024)
                print("SERVER READ", data)
                if data == b'':
                    print('EOF?')
                    break
                buffer.append(data)
                do_flush = False
                while message_buffer.append(buffer):
                    do_flush = True
                    print('<--', message_buffer.content)
                    responses = dispatcher.receive(message_buffer.content)
                    if responses:
                        print('-->', responses.serialize() if isinstance(responses, Message) else responses)
                        dispatcher.send(responses, wfile)
                    message_buffer.reset()
                if do_flush:
                    wfile.flush()
        finally:
            print('close connection', self.client_address)
            self.request.close()


class JsonRpcServer(JsonRpc):
    def serve_forever(self, host: str = 'localhost', port: int = 0):
        self.server = socketserver.ThreadingTCPServer(
            (host, port), JsonRpcHandler)
        print('opening server at:', self.server.socket.getsockname())
        self.server.dispatcher = self
        self.server.daemon_threads = True
        self.server.serve_forever()

