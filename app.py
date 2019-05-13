
from argh import dispatch_command
from trefier.cli.model_cli import ModelCLI

dispatch_command(ModelCLI().run)
