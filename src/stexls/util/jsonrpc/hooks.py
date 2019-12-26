import logging
import functools

log = logging.getLogger(__name__)

__all__ = ['alias', 'request', 'notification', 'method', 'extract_methods']

_JSON_RPC_NAME = 'json_rpc_name'
_JSON_RPC_METHOD = 'json_rpc_method'

def alias(name: str):
    assert name is not None
    def alias_decorator(f):
        log.debug('JsonRpc hook alias %s->%s', f, name)
        f.json_rpc_name = name
        return f
    return alias_decorator

def request(f):
    log.debug('JsonRpc request hook: %s', f)
    
    if not hasattr(f, _JSON_RPC_NAME):
        setattr(f, _JSON_RPC_NAME, f.__name__)

    from .dispatcher import Dispatcher
    @functools.wraps(f)
    def request_wrapper(self: Dispatcher, *args, **kwargs):
        if args and kwargs:
            raise ValueError('Mixing args and kwargs not allowed.')
        f(self, *args, **kwargs)
        method_name = getattr(f, _JSON_RPC_NAME)
        return self.request(method_name, args or kwargs)

    return request_wrapper

def notification(f):
    log.debug('JsonRpc notification hook: %s', f)

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
    log.debug('JsonRpc method hook: %s', f)

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
        if not callable(attr):
            continue
        if not hasattr(attr, _JSON_RPC_METHOD):
            continue
        if not getattr(attr, _JSON_RPC_METHOD, None):
            continue
        method_name = getattr(attr, _JSON_RPC_NAME)
        if method_name in methods:
            raise ValueError(f'Duplicate method with the name "{method_name}".')
        methods[method_name] = attr
        log.debug('Registering method "%s" with %s', method_name, instance)
    return methods
