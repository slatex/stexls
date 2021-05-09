from unittest import IsolatedAsyncioTestCase

from stexls.jsonrpc import exceptions, hooks, dispatcher


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
        (host, port), server_task = await GetSetServer.start_server()
        client: GetSetClient
        client, client_task = await GetSetClient.open_connection(host, port)
        with self.assertRaises(exceptions.InternalErrorException):
            await client.get_value('key name')
        await client.set_value(key='key name', value='some random value')
        self.assertDictEqual(
            await client.get_value('key name'),
            {'key': 'key name', 'value': 'some random value'}
        )
        self.assertDictEqual(
            await client.will_call_server_get_value('key name'),
            {'key': 'key name', 'value': 'some random value'}
        )
