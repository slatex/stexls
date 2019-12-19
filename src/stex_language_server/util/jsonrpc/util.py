from typing import Optional
from .core import *

__all__ = ['validate_json', 'restore_message']

def validate_json(o: object) -> Optional[ResponseObject]:
    ''' Validates a json object.
    Returns:
        Response object with error information if
        the object o is not a valid json rpc message object.
    '''
    if not isinstance(o, dict):
        return ResponseObject(None, error=ErrorObject(ErrorCodes.InvalidRequest))
    INVALID = ResponseObject(o.get('id'), error=ErrorObject(ErrorCodes.InvalidRequest))
    id = 'id' in o
    not_null = id and o['id'] is not None
    method = 'method' in o
    params = 'params' in o
    result = 'result' in o
    error = 'error' in o
    if (
        o.get('jsonrpc') != '2.0'
        or (id and not isinstance(o.get('id'), (int, str)))
        or (method and not isinstance(o['method'], str))
        or (params and not isinstance(o['params'], (list, dict)))
        or (error and (not isinstance(o['error'], dict) or 'code' not in o['error'] or 'message' not in o['error']))):
        return INVALID
    if not (
        ((not_null or not id) and method and not result and not error)
        or (id and not method and not params and result and not error)
        or (id and not method and not params and not result and error)):
        return INVALID


def restore_message(o: object) -> MessageObject:
    ''' Restores the original message from a given json object.
        Assumes that the object is valid.
    Return:
        A valid json rpc message object, assuming
        the input is valid.
    '''
    if 'method' in o:
        if 'id' in o:
            return RequestObject(
                id=o['id'], method=o['method'], params=o.get('params'))
        else:
            return NotificationObject(
                method=o['method'], params=o.get('params'))
    else:
        if 'error' in o:
            error = ErrorObject(
                code=o['error']['code'],
                message=o['error']['message'],
                data=o['error'].get('data', None))
        else:
            error = None
        return ResponseObject(
            id=o.get('id'), result=o.get('result'), error=error)
