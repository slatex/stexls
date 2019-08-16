from __future__ import annotations
from typing import Optional, Callable, List
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

    def return_result(self, command: Callable, status: int, encoder: Optional[json.JSONEncoder] = None, **kwargs):
        """ Returns the result of a command over stdout in json format. """
        kwargs.update({
                "command": command.__name__,
                "status": status
        })
        if encoder is None:
            print(json.dumps(kwargs, default=lambda obj: obj.__dict__), flush=True)
        else:
            print(encoder.encode(kwargs), flush=True)

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
                argh.dispatch_commands([*commands], shlex.split(line))
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
