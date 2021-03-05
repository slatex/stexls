import functools
from typing import Awaitable

__all__ = ['alias', 'request', 'notification', 'method', 'extract_methods']

_JSON_RPC_NAME = 'json_rpc_name'
_JSON_RPC_METHOD = 'json_rpc_method'


def alias(name: str):
    ' Gives a specific json rpc method name to the wrapped method. '
    assert name is not None

    def alias_decorator(f):
        f.json_rpc_name = name
        return f
    return alias_decorator


def request(f):
    ' The wrapped method will create and send requests using the underlying dispatcher. '
    if not hasattr(f, _JSON_RPC_NAME):
        setattr(f, _JSON_RPC_NAME, f.__name__)

    from .dispatcher import Dispatcher

    @functools.wraps(f)
    def request_wrapper(self: Dispatcher, *args, **kwargs) -> Awaitable:
        if args and kwargs:
            raise ValueError('Mixing args and kwargs not allowed.')
        f(self, *args, **kwargs)
        method_name = getattr(f, _JSON_RPC_NAME)
        return self.request(method_name, args or kwargs)

    return request_wrapper


def notification(f):
    ' The wrapped method will create and send notifications using the underlying dispatcher. '
    if not hasattr(f, _JSON_RPC_NAME):
        setattr(f, _JSON_RPC_NAME, f.__name__)

    from .dispatcher import Dispatcher

    @functools.wraps(f)
    def notification_wrapper(self: Dispatcher, *args, **kwargs):
        if args and kwargs:
            raise ValueError('Mixing args and kwargs not allowed.')
        f(self, *args, **kwargs)
        method_name = getattr(f, _JSON_RPC_NAME)
        return self.notification(method_name, args or kwargs)

    return notification_wrapper


def method(f):
    ' Decorator that enables this function to be called remotely. '
    if not hasattr(f, _JSON_RPC_NAME):
        setattr(f, _JSON_RPC_NAME, f.__name__)
    setattr(f, _JSON_RPC_METHOD, True)
    return f


def extract_methods(instance):
    ' Extracts public functions decorated with @method from an instance. '
    methods = {}
    for attr_name in dir(instance):
        if attr_name.startswith('_'):
            continue
        attr = getattr(instance, attr_name)
        if not getattr(attr, _JSON_RPC_METHOD, False):
            continue
        if not callable(attr):
            raise ValueError(f'Not a method: {attr}')
        method_name = getattr(attr, _JSON_RPC_NAME)
        if method_name in methods:
            raise ValueError(
                f'Duplicate method with the name "{method_name}".')
        if not method_name:
            raise ValueError(f'Invalid method name given to method: {attr}')
        methods[method_name] = attr
    return methods
