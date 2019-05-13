import os
import sys
import shlex
import argh
from itertools import chain
import argparse
from pathlib import Path
import itertools

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

    def return_result(self, command, status, **kwargs):
        """ Helper for returning results. """
        extra = ','.join(f'"{arg}":{value}' for arg, value in kwargs.items())
        result = f'{{"command":"{command.__name__}","status":{status}{"," if extra else ""}{extra}}}'
        print(result, flush=True)
        return result

    def run(self, commands, initial_command_list:list=None):
        """ Dispatches given commands and writes caught exceptions to the log file.
        
        Arguments:
            :param commands: Commands to dispatch for each line.
            :param initial_command_list: List of arguments that will be executed before drawing lines froms stdin.
        """
        try:
            for line in chain(initial_command_list or [], sys.stdin):
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
