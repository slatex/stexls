import os
from stex_language_server.util.cli import Cli, Arg, command
from stex_language_server.tagger.client import Client
from stex_language_server.tagger.server import Server


@command(
    ip=Arg(default='localhost'),
    port=Arg(default=0, type=int, help='Port of the server. "0" for random free port.'))
def client(ip:str, port:int):
    print("Connecting client", ip, port)
    c = Client(ip, port)

@command(
    model=Arg(help="Path to model to load."),
    ip=Arg(default='localhost'),
    port=Arg(default=0, type=int, help='Port of the server. "0" for random free port.'))
def server(model:str, ip:str, port:int):
    print("Starting server at", ip, port)
    if not os.path.exists(model):
        raise ValueError(f'Given model path ({model}) does not exists.')
    if not os.path.isfile(model):
        raise ValueError(f'Given model path ({model}) is not a file.')
    s = Server(model, ip, port)

def main():
    cli = Cli([
        client,
        server,
    ], __doc__)

    cli.dispatch()

if __name__ == '__main__':
    main()
else:
    raise RuntimeError("This module must be executed using python -m trefier.")
