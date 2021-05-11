import asyncio
import json
import random
from asyncio.streams import StreamReader, StreamWriter
from pathlib import Path
from unittest import IsolatedAsyncioTestCase

from stexls.jsonrpc.core import ErrorCodes
from stexls.lsp.cli import lsp


class TestLSP(IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.port = random.randint(2048, 65000)
        self.lsp = lsp(port=self.port, transport_kind='tcp')
        self.stub = {
            "jsonrpc": "2.0",
            "id": "test message",
            "method": None,
            "params": {
                'capabilities': {},
                'rootUri': Path('/tmp/stexls-tests-root-dir').as_uri(),
            },
        }

    async def test_initialize(self):
        async def callback(reader: StreamReader, writer: StreamWriter):
            self.stub['id'] = 'initialize'
            self.stub['method'] = 'initialize'
            content = json.dumps(self.stub).encode()
            writer.write(
                f'content-length: {len(content)}\r\n\r\n'.encode() + content)
            raw_content_length = await reader.readline()
            content_length = int(
                raw_content_length.decode().split(':')[-1].strip())
            self.empty_line = await reader.readline()
            raw_response = await reader.readexactly(content_length)
            writer.close()
            self.response = json.loads(raw_response.decode())
            print(self.response)
        server = await asyncio.start_server(callback, host='localhost', port=self.port)
        await self.lsp
        server.close()
        self.assertIn('result', self.response)
        result = self.response['result']
        self.assertIn('capabilities', result)
        self.assertIn('serverInfo', result)
        capabilities = result['capabilities']
        self.assertIn('textDocumentSync', capabilities)
        self.assertTrue(capabilities['completionProvider'])
        self.assertTrue(capabilities['definitionProvider'])
        self.assertTrue(capabilities['referencesProvider'])

    async def test_parse_error(self):
        async def callback(reader: StreamReader, writer: StreamWriter):
            content = b'{ fail to parse'
            writer.write(
                f'content-length: {len(content)}\r\n\r\n'.encode() + content)
            raw_content_length = await reader.readline()
            content_length = int(
                raw_content_length.decode().split(':')[-1].strip())
            self.empty_line = await reader.readline()
            raw_response = await reader.readexactly(content_length)
            writer.close()
            self.response = json.loads(raw_response.decode())
        server = await asyncio.start_server(callback, host='localhost', port=self.port)
        await self.lsp
        server.close()
        self.assertEqual(self.empty_line, b'\r\n')
        self.assertIn('error', self.response)
        self.assertIn('code', self.response['error'])
        self.assertEqual(ErrorCodes.ParseError, self.response['error']['code'])

    async def test_internal_error(self):
        async def callback(reader: StreamReader, writer: StreamWriter):
            self.stub['method'] = 'initialize'
            # If initialize is called without a `rootUri` param, it will raise, causing an InternalError
            del self.stub['params']['rootUri']
            content = json.dumps(self.stub).encode()
            writer.write(
                f'content-length: {len(content)}\r\n\r\n'.encode() + content)
            raw_content_length = await reader.readline()
            content_length = int(
                raw_content_length.decode().split(':')[-1].strip())
            self.empty_line = await reader.readline()
            raw_response = await reader.readexactly(content_length)
            writer.close()
            self.response = json.loads(raw_response.decode())
        server = await asyncio.start_server(callback, host='localhost', port=self.port)
        await self.lsp
        server.close()
        self.assertEqual(self.empty_line, b'\r\n')
        self.assertIn('error', self.response)
        self.assertIn('code', self.response['error'])
        self.assertEqual(ErrorCodes.InternalError,
                         self.response['error']['code'])

    async def test_invalid_params(self):
        # the `initialized` method does not take any parameters: Giving it one will fail.
        async def callback(reader: StreamReader, writer: StreamWriter):
            self.stub['method'] = 'initialized'
            self.stub['params'] = {'invalid param': 0}
            content = json.dumps(self.stub).encode()
            writer.write(
                f'content-length: {len(content)}\r\n\r\n'.encode() + content)
            raw_content_length = await reader.readline()
            content_length = int(
                raw_content_length.decode().split(':')[-1].strip())
            self.empty_line = await reader.readline()
            raw_response = await reader.readexactly(content_length)
            writer.close()
            self.response = json.loads(raw_response.decode())
        server = await asyncio.start_server(callback, host='localhost', port=self.port)
        await self.lsp
        server.close()
        self.assertEqual(self.empty_line, b'\r\n')
        self.assertIn('error', self.response)
        self.assertIn('code', self.response['error'])
        self.assertEqual(ErrorCodes.InvalidParams,
                         self.response['error']['code'])

    async def test_method_not_found(self):
        async def callback(reader: StreamReader, writer: StreamWriter):
            self.stub['method'] = 'this method does not exist'
            content = json.dumps(self.stub).encode()
            writer.write(
                f'content-length: {len(content)}\r\n\r\n'.encode() + content)
            raw_content_length = await reader.readline()
            content_length = int(
                raw_content_length.decode().split(':')[-1].strip())
            self.empty_line = await reader.readline()
            raw_response = await reader.readexactly(content_length)
            writer.close()
            self.response = json.loads(raw_response.decode())
        server = await asyncio.start_server(callback, host='localhost', port=self.port)
        await self.lsp
        server.close()
        self.assertEqual(self.empty_line, b'\r\n')
        self.assertIn('error', self.response)
        self.assertIn('code', self.response['error'])
        self.assertEqual(ErrorCodes.MethodNotFound,
                         self.response['error']['code'])

    async def test_invalid_request(self):
        async def callback(reader: StreamReader, writer: StreamWriter):
            content = json.dumps(
                {'message': 'Hello, World!'}).encode()
            writer.write(
                f'content-length: {len(content)}\r\n\r\n'.encode() + content)
            raw_content_length = await reader.readline()
            content_length = int(
                raw_content_length.decode().split(':')[-1].strip())
            self.empty_line = await reader.readline()
            raw_response = await reader.readexactly(content_length)
            self.response = json.loads(raw_response.decode())
            writer.close()
        server = await asyncio.start_server(callback, host='localhost', port=self.port)
        await self.lsp
        server.close()
        self.assertEqual(self.empty_line, b'\r\n')
        expected_response = {
            'error': {'code': ErrorCodes.InvalidRequest, 'message': 'Invalid Request'},
            'id': None, 'jsonrpc': '2.0'}
        self.assertDictEqual(expected_response, self.response)

    async def test_initialized(self):
        pass
