from typing import Optional
from .core import Message, ResponseMessage, RequestMessage, NotificationMessage, ErrorCodes, ErrorObject

__all__ = ['validate_json', 'restore_message']

def validate_json(o: object) -> Optional[ResponseMessage]:
    ''' Validates a json object.
    Returns:
        Nothing if the object can be as a core.Message
        else returns a ResponseMessage with the error 
        that can be sent back.
    '''
    INVALID = ResponseMessage(o.get('id'), error=ErrorObject(ErrorCodes.InvalidRequest))
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


def restore_message(o: object) -> Message:
    ''' Restores the original message from a given json object.
        Assumes that the object is valid.
    Return:
        Original message, assuming the input is correct.
    '''
    if 'method' in o:
        if 'id' in o:
            return RequestMessage(
                id=o['id'], method=o['method'], params=o.get('params'))
        else:
            return NotificationMessage(
                method=o['method'], params=o.get('params'))
    else:
        if 'error' in o:
            error = ErrorObject(
                code=o['error']['code'],
                message=o['error']['message'],
                data=o['error'].get('data', None))
        else:
            error = None
        return ResponseMessage(
            id=o.get('id'), result=o.get('result'), error=error)
