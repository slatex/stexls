import sys
import inspect
import functools
import argparse
import shlex

__all__ = ['Cli', 'Arg']


class Arg:
    ' Passes init argument through to ArgumentParser.add_argument() '
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

def command(**kwargs):
    ''' Decorator for a function used as a cli command.
        Assign an 'Arg()' to each parameter.
        Example:

        @command(a=Arg('a', type=int, help='help'), b=Arg('--b'))
        def f(a, b:str='test'): pass
    '''
    for _, arg in kwargs.items():
        if not isinstance(arg, Arg):
            raise ValueError("Command kwargs must be of type Arg")
    def decorator(f):
        f.cli_cmd_config = kwargs
        params = inspect.signature(f).parameters
        if not kwargs:
            for param_name, param in params.items():
                kwargs[param_name] = Arg()
        for param_name, arg in kwargs.items():
            param = params.get(param_name)
            if param is not None:
                if 'default' not in arg.kwargs and param.default != inspect._empty:
                    arg.kwargs['default'] = param.default
                if 'action' not in arg.kwargs:
                    if param.default is True:
                        arg.kwargs['action'] = 'store_false'
                    elif param.default is False:
                        arg.kwargs['action'] = 'store_true'
                if 'type' not in arg.kwargs and param.annotation != inspect._empty and param.annotation != bool:
                    arg.kwargs['type'] = param.annotation
            if 'dest' in arg.kwargs and 'default' not in arg.kwargs:
                arg.kwargs['default'] = params[arg.kwargs['dest']].default
            if not arg.args:
                ' Add param to arguments if not already give. If default is in kwargs also prefix with -- '
                if 'default' in arg.kwargs:
                    arg.args = ('--' + param_name,)
                else:
                    arg.args = (param_name,)
        return f
    return decorator

class Cli:
    def __init__(self, commands, description:str):
        self.parser = argparse.ArgumentParser(
            description=description,
            formatter_class=argparse.ArgumentDefaultsHelpFormatter)
        
        class ExtendAction(argparse.Action):
            def __call__(self, parser, namespace, values, option_string=None):
                items = getattr(namespace, self.dest) or []
                items.extend(values)
                setattr(namespace, self.dest, items)
        
        self.parser.register('action', 'extend', ExtendAction)

        self.command_index = {
            command.__name__: command
            for command in commands
        }

        command_subparsers = self.parser.add_subparsers(dest='_command')

        for command_name, command in self.command_index.items():
            if not hasattr(command, 'cli_cmd_config'):
                raise ValueError(f'Invalid command: {command_name}')
            
            sub_command = command_subparsers.add_parser(
                command_name,
                help=command.__doc__,
                formatter_class=argparse.ArgumentDefaultsHelpFormatter)

            sub_command.register('action', 'extend', ExtendAction)

            for param_name, conf in command.cli_cmd_config.items():
                sub_command.add_argument(*conf.args, **conf.kwargs)

    def dispatch(self, argv:list=None):
        args = self.parser.parse_args(argv)
        command = self.command_index.get(args._command)
        if command is None:
            self.parser.print_usage()
            sys.exit(1)
        kwargs = args.__dict__.copy()
        del kwargs['_command']
        return command(**kwargs)