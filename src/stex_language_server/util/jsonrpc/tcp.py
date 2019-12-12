from __future__ import annotations
from typing import Union, Optional, List, Dict, Any
import socket
import socketserver
import threading
import logging
from .core import *
from .jsonrpc import JsonRpcProtocol

__all__ = ['Server', 'Client']

logger = logging.getLogger(__name__)

class JsonRpcRequestHandler(socketserver.BaseRequestHandler):
    def __init__(self, *args, protocol: JsonRpcProtocol = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.protocol = protocol
        logging.debug('Instantiated JRPC Request Handler %s', self.protocol)

    def handle(self):
        logger.info('accepted request from %s', self.client_address)
        self.server.clients.register(self)
        rfile = self.request.makefile('rb', buffering=0)
        wfile = self.request.makefile('wb', buffering=0)
        try:
            self.server.protocol.connected(self.client_address, rfile, wfile)
        except EOFError:
            logger.info('%s disconnected', self.client_address)
        except:
            logger.error()
            logger.exception()
        finally:
            self.server.clients.unregister(self)
            self.request.close()


class Server:
    def __init__(
        self,
        protocol: JsonRpcProtocol,
        host: str = 'localhost',
        port: int = 0,
        shutdown_delay: float = 5.0):
        self._protocol = protocol
        self._shutdown_delay = shutdown_delay
        self._lock = threading.Lock()
        self._is_shutdown = False
        self._timer = None
        self._clients = []
        self._server = socketserver.ThreadingTCPServer(
            (host, port), functools.partial(JsonRpcRequestHandler, protocol=protocol))
        self._server.daemon_threads = True
        self.host, self.port = self._server.socket.getsockname()
    
    def serve_forever(self):
        with self._server:
            logging.info('Started server at tcp://%s:%s', self.host, self.port)
            self._server.serve_forever()
        self._stop_shutdown_timer()
        logging.info('Server stopped serving at tcp://%s:%s', self.host, self.port)
        
    def shutdown(self):
        with self._lock:
            if self._is_shutdown:
                return
            self._is_shutdown = True
        logger.debug('Calling shutdown()')
        self._server.shutdown()
    
    def _stop_shutdown_timer(self):
        if self._timer:
            logger.info('Shutdown aborted')
            self._timer.cancel()
        self._timer = None
    
    def _start_shutdown_timer(self):
        logger.info("Server shutting down in %f", self._shutdown_delay)
        self._stop_shutdown_timer()
        self._timer = threading.Timer(self._shutdown_delay, self.shutdown)
        self._timer.start()
    
    def register(self, client):
        with self._lock:
            if self._is_shutdown:
                return
            self._clients.append(client)
            self._stop_shutdown_timer()
    
    def unregister(self, client):
        with self._lock:
            if self._is_shutdown:
                return
            self._clients.remove(client)
            if not self._clients:
                logger.info("All clients disconnected")
                self._start_shutdown_timer()


class Client:
    def __init__(self, protocol: JsonRpcProtocol, host: str = 'localhost', port: int = 0):
        self.protocol = protocol
        self.host = host
        self.port = port

    def connect(self) -> JsonRpcClient:
        logger.debug('client connecting to %s', (self.host, self.port))
        self.socket = socket.create_connection((self.host, self.port))
        try:
            logger.info('client bound to %s', self.socket.getsockname())
            wfile = self.socket.makefile('wb', buffering=0)
            rfile = self.socket.makefile('rb', buffering=0)
            self.connected((self.host, self.port), rfile, wfile)
        except EOFError:
            logger.info('client disconnected')
        except:
            logger.exception()
        finally:
            self.socket.close()
