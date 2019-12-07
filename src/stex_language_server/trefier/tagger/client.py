''' Implements the "Tagger Server Protocol" client. '''

import socket
import sys

class Client:
    def __init__(self, ip: str = 'localhost', port: int = 0):
        super().__init__()
        self.ip = ip
        self.port = port
