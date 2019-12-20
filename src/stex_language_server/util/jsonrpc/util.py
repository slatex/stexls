from typing import Optional
import logging
from .core import *

log = logging.getLogger(__name__)

__all__ = ['validate_json', 'restore_message']

def validate_json(o: object) -> Optional[ResponseObject]:
    ''' Validates a json object.
    Returns:
        Response object with error information if
        the object o is not a valid json rpc message object.
    '''
    log.debug('Validating object: %s', o)
    if not isinstance(o, dict) or o.get('jsonrpc') != '2.0':
        log.warning('Validated object not a dict or does\'t contain "jsonrpc" member.')
        return ResponseObject(None, error=ErrorObject(ErrorCodes.InvalidRequest))
    is_request = isinstance(o.get('id'), (int, str)) and 'method' in o
    is_notification = 'id' not in o and 'method' in o
    has_error = (
        isinstance(o.get('error'), dict)
        and isinstance(o['error'].get('code'), int)
        and isinstance(o['error'].get('message'), str))
    is_response = (
        isinstance(o.get('id', False), (str, int, type(None)))
        and (('result' in o) != has_error))
    if (is_request + is_notification + is_response) != 1:
        log.warning(
            'Json object is not uniquely request (%s), notification (%s) or response (%s).',
            is_request, is_notification, is_request)
        return ResponseObject(o.get('id'), error=ErrorObject(ErrorCodes.InvalidRequest))

def restore_message(o: object) -> MessageObject:
    ''' Restores the original message from a given json object.
        Assumes that the object is valid.
    Return:
        A valid json rpc message object, assuming
        the input is valid.
    '''
    is_request = isinstance(o.get('id'), (int, str)) and 'method' in o
    if is_request:
        return RequestObject(id=o['id'], method=o['method'], params=o.get('params'))
    is_notification = 'id' not in o and 'method' in o
    if is_notification:
        return NotificationObject(method=o['method'], params=o.get('params'))
    # must be response
    if 'error' in o:
        return ResponseObject(
            o.get('id'), error=ErrorObject(
                code=o['error']['code'],
                message=o['error'].get('message'),
                data=o['error'].get('data')))
    else:
        return ResponseObject(o.get('id'), result=o.get('result'))
