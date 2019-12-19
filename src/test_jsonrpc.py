import argparse
import threading
import asyncio
import logging

parser = argparse.ArgumentParser()
parser.add_argument('mode', choices=['server', 'client'])
parser.add_argument('--port', type=int, default=10000)
parser.add_argument('--host', default='localhost')
parser.add_argument('--shared', action='store_true')
parser.add_argument('--loglevel', default='warning', type=lambda x: getattr(logging, x.upper(), logging.WARNING))
args = parser.parse_args()

logging.basicConfig(level=args.loglevel)
from stex_language_server.util.jsonrpc.tcp.client import Client
from stex_language_server.util.jsonrpc.tcp.server import Server
from stex_language_server.util.jsonrpc.dispatcher import Dispatcher
from stex_language_server.util.jsonrpc.hooks import *

class ClientDispatcher(Dispatcher):
    @request
    def echo(self, *msg): pass
    @request
    def get(self, x): pass
    @notification
    def set(self, x, value): pass
    @request
    def invalid(self, *args): pass

global_values = {}
class ServerDispatcher(Dispatcher):
    def __init__(self, target):
        super().__init__(target)
        if args.shared:
            self.values = global_values
        else:
            self.values = {}
    @method
    def echo(self, *msg):
        print('echo', *msg)
        return msg, self.values
    @method
    def get(self, x):
        return self.values[x]
    @method
    def set(self, x, value):
        self.values[x] = value

if args.mode == 'server':
    server = Server(ServerDispatcher)
    asyncio.run(server.serve_forever(args.host, args.port))
elif args.mode == 'client':
    client_parser = argparse.ArgumentParser()
    client_parser.add_argument('method')
    client_parser.add_argument('args', nargs='*', default=[])
    import shlex
    async def main():
        client = Client(ClientDispatcher)
        dispatcher, done = await client.open_connection(args.host, args.port)
        while True:
            print('> ', end='')
            ln = input().strip()
            if ln in ('exit', 'quit'):
                break
            if not ln:
                continue
            cmd = client_parser.parse_args(shlex.split(ln))
            try:
                f = getattr(dispatcher, cmd.method)
                print(await f(*cmd.args))
            except Exception as e:
                print(e)
        print('Waiting until done.')
        print(await done)
    asyncio.run(main())