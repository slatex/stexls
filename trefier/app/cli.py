from __future__ import annotations
from typing import Optional, Callable, List, Dict
import sys
import shlex
import argh
import json

__all__ = ['CLI', 'CLIException', 'CLIExitException','CLIRestartException']


class CLIException(Exception):
    """ Exception thrown by the cli. """
    pass


class CLIExitException(CLIException):
    """ Exception thrown when the user wishes to exit the program. """
    pass


class CLIRestartException(CLIException):
    """ Exception thrown in order to restart the infinite loop. """
    pass


class CLI:
    """ Contains basic pattern of argh.dispatch_commands in a for line in stdin loop and error handling. """
    def __init__(self):
        self._serialize_output = False
    
    def set_output_serialization(self, value: bool):
        """ Enables or disables the serialization of the value returned through return_result(). """
        self._serialize_output = value

    def return_result(self, command: Callable, status: int, encoder: Optional[json.JSONEncoder] = None, formatter: Optional[Callable[[Dict], str]] = None, **kwargs):
        """ Returns the result of a command over stdout in json format if serialization was enabled by calling set_output_serialization().
        This function defines a unified way to properly return something to the command line in a way, that does not infere with argh or the cli.

        Arguments:
            :param command: The command function from which to return. 
            :param status: A command status indicator value.
        
        Keyword Arguments:
            :param encoder: An optional specific JSON encoder. Requires set_output_serialization(True) called. The default json encoder will be used if None is set.
            :param formatter: Formatter for the return result as a string. Requires set_output_serialization(False) or nothing as serialization is False by default.
            :param kwargs: The dictionary that should be returned.
        """
        kwargs.update({
                "command": command.__name__,
                "status": status
        })
        if self._serialize_output:
            if encoder is None:
                print(json.dumps(kwargs, default=lambda obj: obj.__dict__), flush=True)
            else:
                print(encoder.encode(kwargs), flush=True)
        elif formatter is not None:
            print(formatter(kwargs))
        else:
            print(kwargs, flush=True)

    def run(self, commands: List[Callable]):
        """ Runs the cli.
        Arguments:
            :param commands: Commands available.
        """
        while True:
            status = self.dispatch(commands)
            if not status:
                break
    
    def dispatch(self, commands: List[Callable]):
        """ Runs a single command with this cli, then returns wether the command indicated continuation or not.
            Arguments:
                :param commands: Commands available.
        """
        try:
            line = None
            for line in sys.stdin:
                break
            try:
                argh.dispatch_commands(commands, shlex.split(line))
            except SystemExit:
                return True
            except CLIExitException:
                return False
            except CLIRestartException:
                raise
        except KeyboardInterrupt:
            return False
        except StopIteration:
            return False
        return True
    
    def exit(self):
        """ Exits the CLI. """
        raise CLIExitException()
    
    def restart(self):
        """ Restarts the cli. """
        raise CLIRestartException()

    @argh.arg('message', nargs='?', default='')
    def echo(self, message):
        """ Returns the message. """
        self.return_result(self.echo, 0, message=message)
