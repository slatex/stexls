import asyncio
import traceback
from asyncio.tasks import wait_for
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
        self.lsp = lsp(
            port=self.port,
            transport_kind='tcp',
            enable_global_validation=True,
            lint_workspace_on_startup=True,
            enable_trefier=True,
            num_jobs=4,
        )
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
        self.server, self.language_server_connection = await self.lsp
        await self.language_server_connection
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
        self.server, self.language_server_connection = await self.lsp
        await self.language_server_connection
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
        self.server, self.language_server_connection = await self.lsp
        await self.language_server_connection
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
        self.server, self.language_server_connection = await self.lsp
        await self.language_server_connection
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
        self.server, self.language_server_connection = await self.lsp
        await self.language_server_connection
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
        self.server, self.language_server_connection = await self.lsp
        await self.language_server_connection
        server.close()
        self.assertEqual(self.empty_line, b'\r\n')
        expected_response = {
            'error': {'code': ErrorCodes.InvalidRequest, 'message': 'Property "jsonrpc" is missing.'},
            'id': None,
            'jsonrpc': '2.0'}
        self.assertDictEqual(expected_response, self.response)

    async def test_initialization(self):
        root_path = Path("/home/re15tygi/source/stexls/downloads")
        work_done_progress_enabled = False
        initialization_options = {"test_option": "test value"}
        client_initialization_message = {
            "jsonrpc": "2.0",
            "id": 0,
            "method": "initialize",
            "params": {
                "processId": 13854,
                "clientInfo": {
                    "name": "vscode",
                    "version": "1.56.0"
                },
                "rootPath": root_path.as_posix(),
                "rootUri": root_path.as_uri(),
                "capabilities": {
                    "workspace": {
                        "applyEdit": True,
                        "workspaceEdit": {
                            "documentChanges": True,
                            "resourceOperations": [
                                "create",
                                "rename",
                                "delete"
                            ],
                            "failureHandling": "textOnlyTransactional"
                        },
                        "didChangeConfiguration": {
                            "dynamicRegistration": True
                        },
                        "didChangeWatchedFiles": {
                            "dynamicRegistration": True
                        },
                        "symbol": {
                            "dynamicRegistration": True,
                            "symbolKind": {
                                "valueSet": [
                                    1,
                                    2,
                                    3,
                                    4,
                                    5,
                                    6,
                                    7,
                                    8,
                                    9,
                                    10,
                                    11,
                                    12,
                                    13,
                                    14,
                                    15,
                                    16,
                                    17,
                                    18,
                                    19,
                                    20,
                                    21,
                                    22,
                                    23,
                                    24,
                                    25,
                                    26
                                ]
                            }
                        },
                        "executeCommand": {
                            "dynamicRegistration": True
                        },
                        "configuration": True,
                        "workspaceFolders": True
                    },
                    "textDocument": {
                        "publishDiagnostics": {
                            "relatedInformation": True,
                            "versionSupport": False,
                            "tagSupport": {
                                "valueSet": [
                                    1,
                                    2
                                ]
                            }
                        },
                        "synchronization": {
                            "dynamicRegistration": True,
                            "willSave": True,
                            "willSaveWaitUntil": True,
                            "didSave": True
                        },
                        "completion": {
                            "dynamicRegistration": True,
                            "contextSupport": True,
                            "completionItem": {
                                "snippetSupport": True,
                                "commitCharactersSupport": True,
                                "documentationFormat": [
                                    "markdown",
                                    "plaintext"
                                ],
                                "deprecatedSupport": True,
                                "preselectSupport": True,
                                "tagSupport": {
                                    "valueSet": [
                                        1
                                    ]
                                }
                            },
                            "completionItemKind": {
                                "valueSet": [
                                    1,
                                    2,
                                    3,
                                    4,
                                    5,
                                    6,
                                    7,
                                    8,
                                    9,
                                    10,
                                    11,
                                    12,
                                    13,
                                    14,
                                    15,
                                    16,
                                    17,
                                    18,
                                    19,
                                    20,
                                    21,
                                    22,
                                    23,
                                    24,
                                    25
                                ]
                            }
                        },
                        "hover": {
                            "dynamicRegistration": True,
                            "contentFormat": [
                                "markdown",
                                "plaintext"
                            ]
                        },
                        "signatureHelp": {
                            "dynamicRegistration": True,
                            "signatureInformation": {
                                "documentationFormat": [
                                    "markdown",
                                    "plaintext"
                                ],
                                "parameterInformation": {
                                    "labelOffsetSupport": True
                                }
                            },
                            "contextSupport": True
                        },
                        "definition": {
                            "dynamicRegistration": True,
                            "linkSupport": True
                        },
                        "references": {
                            "dynamicRegistration": True
                        },
                        "documentHighlight": {
                            "dynamicRegistration": True
                        },
                        "documentSymbol": {
                            "dynamicRegistration": True,
                            "symbolKind": {
                                "valueSet": [
                                    1,
                                    2,
                                    3,
                                    4,
                                    5,
                                    6,
                                    7,
                                    8,
                                    9,
                                    10,
                                    11,
                                    12,
                                    13,
                                    14,
                                    15,
                                    16,
                                    17,
                                    18,
                                    19,
                                    20,
                                    21,
                                    22,
                                    23,
                                    24,
                                    25,
                                    26
                                ]
                            },
                            "hierarchicalDocumentSymbolSupport": True
                        },
                        "codeAction": {
                            "dynamicRegistration": True,
                            "isPreferredSupport": True,
                            "codeActionLiteralSupport": {
                                "codeActionKind": {
                                    "valueSet": [
                                        "",
                                        "quickfix",
                                        "refactor",
                                        "refactor.extract",
                                        "refactor.inline",
                                        "refactor.rewrite",
                                        "source",
                                        "source.organizeImports"
                                    ]
                                }
                            }
                        },
                        "codeLens": {
                            "dynamicRegistration": True
                        },
                        "formatting": {
                            "dynamicRegistration": True
                        },
                        "rangeFormatting": {
                            "dynamicRegistration": True
                        },
                        "onTypeFormatting": {
                            "dynamicRegistration": True
                        },
                        "rename": {
                            "dynamicRegistration": True,
                            "prepareSupport": True
                        },
                        "documentLink": {
                            "dynamicRegistration": True,
                            "tooltipSupport": True
                        },
                        "typeDefinition": {
                            "dynamicRegistration": True,
                            "linkSupport": True
                        },
                        "implementation": {
                            "dynamicRegistration": True,
                            "linkSupport": True
                        },
                        "colorProvider": {
                            "dynamicRegistration": True
                        },
                        "foldingRange": {
                            "dynamicRegistration": True,
                            "rangeLimit": 5000,
                            "lineFoldingOnly": True
                        },
                        "declaration": {
                            "dynamicRegistration": True,
                            "linkSupport": True
                        },
                        "selectionRange": {
                            "dynamicRegistration": True
                        }
                    },
                    "window": {
                        "workDoneProgress": work_done_progress_enabled
                    }
                },
                "initializationOptions": initialization_options,
                "trace": "off",
                "workspaceFolders": [
                    {
                        "uri": root_path.as_uri(),
                        "name": "downloads"
                    }
                ]
            }
        }

        def send_initialize(writer):
            content = json.dumps(client_initialization_message).encode()
            writer.write(
                f'content-length: {len(content)}\r\n\r\n'.encode() + content)

        def send_initialized(writer: StreamWriter):
            initialized_params = {'jsonrpc': '2.0',
                                  'method': 'initialized', 'params': {}}
            content = json.dumps(initialized_params).encode()
            writer.write(
                f'content-length: {len(content)}\r\n\r\n'.encode() + content)

        async def wait_for_response(reader: StreamReader):
            raw_content_length = await reader.readline()
            content_length = int(
                raw_content_length.decode().split(':')[-1].strip())
            empty_line = await reader.readline()
            raw_response = await reader.readexactly(content_length)
            response = json.loads(raw_response.decode())
            return response

        self.err = None

        async def client(reader: StreamReader, writer: StreamWriter):
            send_initialize(writer)
            response = await wait_for_response(reader)
            print(response)
            send_initialized(writer)
            response = await wait_for_response(reader)
            print(response)
            try:
                for i in range(3000):
                    response = await wait_for(wait_for_response(reader), timeout=15)
                    print(i, response)
            except Exception as err:
                self.err = err
                traceback.print_exc()
            finally:
                writer.close()
        client_connection = await asyncio.start_server(client, host='localhost', port=self.port)
        self.server, self.language_server_connection = await self.lsp
        await self.language_server_connection
        if self.err:
            raise self.err
        client_connection.close()
