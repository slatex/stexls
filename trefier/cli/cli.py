import os
import sys
import shlex
import argh
from itertools import chain
import argparse
from pathlib import Path
import itertools
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

    def return_result(self, command, status, encoder=None, **kwargs):
        """ Returns the result of a command over stdou in json format. """
        kwargs.update({
                "command": command.__name__,
                "status": status
        })
        print(json.dumps(kwargs, default=lambda obj: obj.__dict__) if encoder is None else encoder.encode(kwargs), flush=True)

    def run(self, commands):
        """ Runs the cli.
        Arguments:
            :param commands: Commands available.
        """
        try:
            for line in sys.stdin:
                try:
                    argh.dispatch_commands(commands + [self.exit, self.echo], shlex.split(line))
                except SystemExit:
                    pass
                except CLIExitException:
                    return
                except CLIRestartException:
                    raise
        except KeyboardInterrupt:
            return
    
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
