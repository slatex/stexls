import argparse
from stex_language_server.util.jsonrpc.tcp import *

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default='localhost')
    parser.add_argument('--port', type=int, default=0)
    subparser = parser.add_subparsers(dest='mode', required=True)
    client_parser = subparser.add_parser('client')
    client_methods = client_parser.add_subparsers(required=True, dest='method')
    client_add = client_methods.add_parser('add')
    client_add.add_argument('items', nargs='+', type=int)
    client_prod = client_methods.add_parser('prod')
    client_prod.add_argument('a', type=float)
    client_prod.add_argument('b', type=float)
    server_parser = subparser.add_parser('server')

    args = parser.parse_args()

    if args.mode == 'client':
        pass
    elif args.mode == 'server':
        JsonRpcTcp().server_forever(args.port, args.host)
