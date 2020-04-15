'''
This package contains core structure for jsonrpc 2.0
and implementations of the protocol using http as well as tcp.

To create a server or a client you simply extend from the Dispatcher class.

>>> class Server(Dispatcher):
>>>    pass

To add methods, declare a method and decorate it with the @method decorator.
This allows the dispatcher to handle incoming messages with the same name using
the decorated method

>>> class Server(Dispatcher):
>>>     @method
>>>     def sum(self, *args):
>>>         return sum(args)
>>>     @method
>>>     def notify(self, *args):
>>>         print('Server received notification:', *args)
>>>     @method
>>>     @alias('special/aliased')
>>>     def aliased(self, *args):
>>>         return *args

This example creates a method "sum" which takes a list of arguments,
sums them up and returns them. The result is automatically sent
back to the callee if the incoming message was marked as a request.
If the callee used a notification, the result is thrown away silently.
The notify method is an example for a method that is expected to be
called using notification messages. It simply prints the arguments
on the server side and returns None. If the incoming message was
a notification, then the None result will be thrown away.
You can give methods a new name with @alias.

To start the server use the dispatcher's method "start_server".

>>> (host, port), server_task = await Server.start_server(host='localhost', port=0)

This will run the server on a free port at localhost.
Notice, that start_server is a classmethod and uses the class of the Server.
The start_server method returns a tuple with the information
about the host and port the server was bound. Use this to retrieve the
port the OS automatically chose for you in case you used port=0.
The server_task is a asyncio task, which runs in the background using
asyncio. Await this in case you don't have anything else to await.
If you don't await, python will not be able to switch to this task and
never actually run the server.

To create a client, just extend from the Dispatcher, again.
A client uses the request and notification decorators to create
remote function hooks.

>>> class Client(Dispatcher):
>>>     @request
>>>     def sum(self, *args): pass
>>>     @notification
>>>     def notify(self, message): pass
>>>     @request
>>>     @alias('special/aliased')
>>>     def this_will_use_alias_name_instead(self, *args): pass

This client implements the request "sum" and
the notification "notify". The function bodies are a "pass" as
they will never be called. The decorators catch calls to these
functions and convert them into the specified message type.
RequestMessage for @request sum, and NotificationMessage for
@notification notify.

You can start the client the same way the server is started.
But instead use the open_connection method.

>>> client, connection = await Client.open_connection(host=host, port=port)

"open_connection" takes a host and a port again. But in order to connect the server with the
client, we need to use the same "host" and "port" values we received from the start_server()
method.
"open_connection" returns an instance of a dispatcher and an asyncio task with the connection.
Again, "open_connection" is a classmethod and requires to be called using the client's class.

You can use the created dispatcher instance to actually call these methods now.

>>> await client.sum(1, 2, 3)
6
>>> client.notify('Hello, World from the client!')
>>> import asyncio
>>> await asyncio.sleep(0)
Server received notification: Hello, World from the client!
>>> await client.this_will_use_alias_name_instead(42, {'member': 'test'})
[42, {'member': 'test'}]

The with @request decorated methods return futures. So remember to use await.
@notification will return None and can't be await. In this example I use
await asyncio.sleep(0) to trigger the serverside handling.
The aliased method works like the others, except that the called remote
method will not have the same name as the method called.
The client calls "this_will_use_alias_name_instead", but the server
will receive a message with the method name "special/aliased" and execute it.

To stop the client, use cancel() on the connection task object.

>>> connection.cancel()

To stop the server, use the server_task's "cancel" method.

>>> server_task.cancel()

'''

from .dispatcher import Dispatcher
from .hooks import alias, method, notification, request

__all__ = ['Dispatcher', 'alias', 'method', 'notification', 'request']