from argh import *
import argparse
from glob import glob
from os.path import isdir, expanduser
import itertools
from loguru import logger
import argh

from trefier.misc.location import *
from trefier.misc.Cache import Cache
from trefier.linting.linter import Linter
from trefier.app.cli import CLI

__all__ = ['LinterCLI']


class LinterCLI(CLI):
    @arg('directories',
         nargs=argparse.REMAINDER,
         type=lambda x: glob(x, recursive=True),
         help="List of directories to add to watched list.")
    @aliases('add')
    def add_directories(self, directories):
        self.logger.info(f"Adding directories")
        added = 0
        rejected = 0
        try:
            for directory in itertools.chain(*directories):
                if isdir(directory):
                    added += 1
                    self.logger.info(f"Adding {directory}")
                    self.linter.add_directory(directory)
                else:
                    self.logger.info(f"Rejecting {directory}")
                    rejected += 1
            self.return_result(
                self.add_directories, 0,
                message=f'Added {added} directories and rejected {rejected} non-directories.')
        except Exception as e:
            self.logger.exception("Exception during add_directory")
            self.return_result(self.add_directories, 1, message=str(e))
    
    @arg('-j', '--jobs', type=int, help="Number of jobs to help parsing tex files.")
    @arg('-d', '--debug', help="Enables debug mode")
    def update(self, jobs=None, debug=False):
        self.logger.info(f"Updating linter jobs={jobs} debug={debug}")
        try:
            num_changed = self.linter.update(jobs, debug)
            self.logger.info(f"{num_changed} files changed")
            self.changed = num_changed != 0
            self.return_result(self.update, 0, message=f'{num_changed} files updated')
        except Exception as e:
            self.logger.exception("Exception thrown during update")
            self.return_result(self.update, 1, message=str(e))

    @arg('path', help="Path to a tagger model")
    def load_tagger(self, path: str):
        self.logger.info(f'load_tagger from "{path}"')
        try:
            self.linter.load_tagger_model(path)
            self.return_result(self.load_tagger, 0, settings=self.linter.tagger.settings)
        except Exception as e:
            self.logger.exception("Exception during load_tagger")
            self.return_result(self.load_tagger, 1, message=str(e))

    def setup(self):
        self._setup_called = True
        self.changed = False
        self.logger = logger.bind(name="model_cli")
        self.logger.add(expanduser('~/.trefier/database_cli.log'), enqueue=True)
        self.logger.info("Beginning session")
        self.return_result(self.setup, 0)

    def run(self, *extra_commands):
        if not self._setup_called:
            raise Exception("linter_cli.setup() must be called before running")
        self.logger.info(f"linter_cli.run with {len(extra_commands)} extra commands")
        super().run([
            self.add_directories,
            self.update,
            self.load_tagger,
            *extra_commands
        ])

    def return_result(self, command, status, encoder=None, **kwargs):
        try:
            self.logger.info(f"Returning {command.__name__} with status {status}")
            return super().return_result(command, status, encoder=encoder or LinterJSONEncoder(), **kwargs)
        except Exception as e:
            self.logger.exception(f"Exception thrown during return_result of {command.__name__}")
            super().return_result(command, 1, message=str(e))

    def __init__(self):
        super().__init__()
        self.logger = None
        self.changed = False
        self._setup_called = False
        self.linter = Linter()

    def __setstate__(self, state):
        self.logger = None
        self.changed = False
        self._setup_called = False
        self.linter = state

    def __getstate__(self):
        return self.linter


class LinterJSONEncoder(json.JSONEncoder):
    def default(self, obj):  # pylint: disable=E0202
        if isinstance(obj, Position):
            return {"line": obj.line, "column": obj.column}
        if isinstance(obj, Range):
            return {"begin": obj.begin, "end": obj.end}
        if isinstance(obj, Location):
            return {"file": obj.file, "range": obj.range}
        raise Exception("Object is not serializable")


if __name__ == '__main__':
    @argh.arg('--cache', help="Name of the file used as cache")
    def _main(cache: str = None):
        with Cache(cache, LinterCLI) as cache:
            cache.data.setup()
            try:
                cache.data.run()
            finally:
                cache.write_on_exit = cache.write_on_exit and cache.data.changed
    argh.dispatch_command(_main)
