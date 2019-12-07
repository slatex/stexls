''' Implements the server part of the "Tagger Server Protocol" '''

import socket

class Server:
    def __init__(self, ip: str = 'localhost', port: int = 0):
        super().__init__()
        self.ip = ip
        self.port = port
