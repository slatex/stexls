import asyncio
import json
import random
from asyncio.streams import StreamReader, StreamWriter
from unittest import IsolatedAsyncioTestCase

from stexls.lsp.cli import lsp


class TestLSP(IsolatedAsyncioTestCase):
    async def test_start(self):
        port = random.randint(2048, 65000)

        lsp_task = lsp(port=port, transport_kind='tcp')

        async def callback(reader: StreamReader, writer: StreamWriter):
            content = json.dumps(
                {'message': 'Hello, World!'}).encode()
            writer.write(
                f'content-length: {len(content)}\r\n\r\n'.encode() + content)
            raw_content_length = await reader.readline()
            content_length = int(
                raw_content_length.decode().split(':')[-1].strip())
            self.assertEqual(content_length, 87)
            empty_line = await reader.readline()
            self.assertEqual(empty_line, b'\r\n')
            response = await reader.readexactly(content_length)
            obj = json.loads(response.decode())
            expected_response = {
                'error': {'code': -32600, 'message': 'Invalid Request'},
                'id': None, 'jsonrpc': '2.0'}
            self.assertDictEqual(expected_response, obj)
            writer.close()
        server = await asyncio.start_server(callback, host='localhost', port=port)
        await lsp_task
        server.close()
