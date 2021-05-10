import logging
from socket import socketpair
from unittest import IsolatedAsyncioTestCase

from stexls.jsonrpc import dispatcher, exceptions, hooks


class GetSetServer(dispatcher.Dispatcher):
    @hooks.method
    def get_value(self, key):
        if not hasattr(self, key):
            raise ValueError(key)
        return {'key': key, 'value': getattr(self, key, 'undefined')}

    @hooks.method
    def set_value(self, key, value):
        setattr(self, key, value)


class GetSetClient(dispatcher.Dispatcher):
    @hooks.request
    def get_value(self, key):
        pass

    @hooks.notification
    def set_value(self, key, value):
        pass

    @hooks.request
    @hooks.alias('get_value')
    def will_call_server_get_value(self, key):
        pass


class TestJRPC(IsolatedAsyncioTestCase):
    async def test_get_set(self):
        logging.basicConfig(
            filename='/tmp/test_get_set.log', level=logging.DEBUG)
        (host, port), server_task = await GetSetServer.start_server()
        client: GetSetClient
        client, client_task = await GetSetClient.open_connection(host, port)
        expected_key = 'key name'
        with self.assertRaises(exceptions.InternalErrorException):
            await client.get_value(expected_key)
        expected_value = 'some expected value'
        await client.set_value(key=expected_key, value=expected_value)
        self.assertDictEqual(
            await client.get_value(expected_key),
            {'key': expected_key, 'value': expected_value}
        )
        self.assertDictEqual(
            await client.will_call_server_get_value(expected_key),
            {'key': expected_key, 'value': expected_value}
        )
        server_task.cancel()
        await client_task

    async def test_ipc(self):
        logging.basicConfig(filename='/tmp/test_ipc.log', level=logging.DEBUG)
        server_read, client_write = socketpair()
        client_read, server_write = socketpair()
        client: GetSetClient
        server: GetSetServer
        server, server_task = await GetSetServer.open_ipc_connection(server_read.fileno(), server_write.fileno())
        client, client_task = await GetSetClient.open_ipc_connection(client_read.fileno(), client_write.fileno())
        self.assertIsInstance(client, GetSetClient)
        self.assertIsInstance(server, GetSetServer)
        expected_key = 'expected-key'
        expected_value = 10
        with self.assertRaises(exceptions.InternalErrorException):
            await client.get_value(key=expected_key)
        await client.set_value(key=expected_key, value=expected_value)
        value = await client.get_value(key=expected_key)
        self.assertDictEqual(
            value, {'key': expected_key, 'value': expected_value})
        server_task.cancel()
        await client_task
