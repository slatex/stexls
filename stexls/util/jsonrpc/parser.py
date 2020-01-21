""" Parser for message objects from json string. """
from typing import List, Optional, Callable, Any
import json
from .core import MessageObject, RequestObject, NotificationObject, ResponseObject, ErrorObject, ErrorCodes


__all__ = ['MessageParser']


class MessageParser:
    ' A parses that parses json objects to jrpc message objects. '
    def __init__(self, o: Any):
        """Parses a json object as a message or batch of messages.

        Args:
            o (Any): Json object.
        """
        self.valid: List[MessageObject] = []
        self.errors: List[ResponseObject] = []
        self.is_batch: bool = False
        invalid = validate_json(o)
        if invalid is not None:
            self.errors.append(invalid)
        elif isinstance(o, dict):
            self.valid.append(restore_message(o))
        elif isinstance(o, list):
            self.is_batch = True
            for item in o:
                invalid = validate_json(item)
                if invalid is None:
                    self.valid.append(restore_message(item))
                else:
                    self.errors.append(invalid)

    def make_responses(self, message_handler: Callable[[MessageObject], Optional[ResponseObject]]) -> List[ResponseObject]:
        """ Shortcut for handling valid messages and appending the invalid inputs to the responses of the handler.

        Args:
            message_handler (Callable[[MessageObject], Optional[ResponseObject]]): A handler that handles any type of input message.

        Returns:
            List[ResponseObject]: List of generated responses that need to be sent. Falsy if nothing needs to be sent.
        """
        handle_op = filter(None, map(message_handler, self.valid))
        if self.is_batch:
            return list(handle_op) + self.errors
        elif self.errors and self.errors[0].id is not None:
            return self.errors
        elif self.valid:
            return list(handle_op)


def validate_json(o: Any) -> Optional[ResponseObject]:
    """Validates a json object.

    Args:
        o (Any): A json object.

    Returns:
        Optional[ResponseObject]: A response message with error information if the input object is invalid.
    """
    if not isinstance(o, dict) or o.get('jsonrpc') != '2.0':
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
        return ResponseObject(o.get('id'), error=ErrorObject(ErrorCodes.InvalidRequest))

def restore_message(o: object) -> MessageObject:
    """ Restores the original MessageObject assuming the input object is a valid representation of one.

    Args:
        o (object): Message object as json dictionary.

    Returns:
        MessageObject: Restored message object.
    """
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
