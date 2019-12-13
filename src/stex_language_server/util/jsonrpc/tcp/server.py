import asyncio
import logging

logging.basicConfig(level=logging.DEBUG)
log = logging.getLogger(__name__)

async def main(host: str = 'localhost', port: int = 0):
    server = await asyncio.start_server(
        json_rpc_protocol, host, port)
    log.info('Starting server at %s', server.sockets[0].getsockname())
    async with server:
        await server.serve_forever()

asyncio.run(main(port=10000))