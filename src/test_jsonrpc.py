import argparse
import threading
import asyncio
import logging
logging.basicConfig(level=logging.DEBUG)
parser = argparse.ArgumentParser()
parser.add_argument('mode', choices=['server', 'client'])
parser.add_argument('--port', type=int, default=10000)
parser.add_argument('--host', default='localhost')
parser.add_argument('--method', default='echo')
parser.add_argument('--args', nargs='*', default=[])
args = parser.parse_args()

from stex_language_server.util.jsonrpc.tcp.protocol import JsonRpcProtocol
from stex_language_server.util.jsonrpc.dispatcher import DispatcherBase, method, notification, request

class ClientDispatcher(DispatcherBase):
    def __init__(self):
        super().__init__()
        self.values = {}
    @request
    def echo(self, *msg): pass
    @request
    def get(self, x): pass
    @notification
    def set(self, x, value): pass
    @request
    def invalid(self, *args): pass

class ServerDispatcher(DispatcherBase):
    def __init__(self):
        super().__init__()
        self.values = {}
    @method
    def echo(self, *msg):
        print('echo', *msg)
        return msg
    @method
    def get(self, x):
        return self.values.get(x)
    @method
    def set(self, x, value):
        self.values[x] = value

if args.mode == 'server':
    dispatcher = ServerDispatcher()
    server = JsonRpcProtocol(dispatcher).serve_forever(
        args.host, args.port)
    asyncio.run(server)
elif args.mode == 'client':
    async def main():
        dispatcher = ClientDispatcher()
        protocol = JsonRpcProtocol(dispatcher)
        connection = protocol.open_connection(args.host, args.port)
        client_task = asyncio.create_task(connection)
        result = getattr(dispatcher, args.method)(*args.args)
        try:
            print("RESULT", await result)
        except Exception as e:
            print("RESULT EXCEPTION", e)
        print('ECHo', await dispatcher.echo('Hello, World!'))
        print('Get', await dispatcher.get('x'))
        print('Set', await dispatcher.set('x', 'Hello, World!'))
        print('Get', await dispatcher.get('x'))
        await client_task

    asyncio.run(main())