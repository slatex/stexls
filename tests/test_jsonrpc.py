#!/usr/bin/env python
import sys
from argparse import ArgumentParser
from stexls.util.jsonrpc import *
import asyncio
import logging

LOG = logging.getLogger(__name__)

class Server(Dispatcher):
    notify_count = 0

    @method
    def echo(self, x):
        LOG.info('Server calling echo(%s, %s)', x, Server.notify_count)
        if x == 'raise':
            raise RuntimeError('This is an exception')
        return x
    
    @method
    def notify(self, *args):
        LOG.info('Server notified: %s', args)
        Server.notify_count += 1
    
    @request
    def info(self, i):
        LOG.info('Server requesting info from client about %s', i)


class Client(Dispatcher):
    @request
    def echo(self, x): LOG.info('Client sending request for echo of %s', x)

    @notification
    def notify(self, *args): LOG.info('Client sending notification about %s', args)

    @method
    def info(self, i):
        response = i*2
        LOG.info('Client received info request about %s: Responding with %s', i, response)
        return response

parser = ArgumentParser()
parser.add_argument('--port', '-p', type=int, default=0)
parser.add_argument('--host', default='localhost')
parser.add_argument('--mode', '-m', choices=('server', 'client'), required=True)
parser.add_argument('--loglevel', '-l', choices=('error', 'warning', 'info', 'debug'), default='warning')

args = parser.parse_args()

async def main():
    logging.basicConfig(level=getattr(logging, args.loglevel.upper()))
    if args.mode == 'client':
        if args.port <= 0:
            raise ValueError('Client needs port other than 0')
        dispatcher, task = await Client.open_connection(args.host, args.port)
        LOG.info('Client connected %s: Running on task %s', dispatcher, task)
        for line in sys.stdin:
            response = dispatcher.echo(line.strip())
            try:
                print('Response from server:', await response)
            except Exception as e:
                print('Exception raised by server:', e)
        await task
    elif args.mode == 'server':
        name, task = await Server.start_server(args.host, args.port)
        LOG.info('main: Server started at %s: Running on task %s', name, task)
        await task
    else:
        raise ValueError(f'Mode: {args.mode}')
    LOG.warning('Main finished.')

asyncio.run(main())