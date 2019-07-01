from argh import *
import argparse
from glob import glob
from os.path import isdir, expanduser
import itertools
from loguru import logger
from functools import wraps
import argh
import threading
import sys

from trefier.misc.location import *
from trefier.linting.symbols import ModuleIdentifier
from trefier.misc.Cache import Cache
from trefier.linting.linter import Linter
from trefier.app.cli import CLI

__all__ = ['LinterCLI']


class LinterCLI(CLI):
    @arg('directories',
         nargs=argparse.REMAINDER,
         type=lambda x: glob(x, recursive=True),
         help="List of directories to add to watched list.")
    def add(self, directories):
        self.logger.info(f"Adding directories")
        added = 0
        rejected = 0
        try:
            for directory in itertools.chain(*directories):
                if isdir(directory):
                    added += 1
                    self.logger.info(f"Adding {directory}")
                    self.linter.add(directory)
                else:
                    self.logger.info(f"Rejecting {directory}")
                    rejected += 1
            self.return_result(self.add, 0, message=f'Added {added}, rejected {rejected}')
        except Exception as e:
            #if __debug__: raise
            self.logger.exception("Exception during add_directory")
            self.return_result(self.add, 1, message=str(e))

    @arg('-j', '--jobs', type=int, help="Number of jobs to help parsing tex files.")
    @arg('-d', '--debug', help="Enables debug mode")
    def update(self, jobs=None, debug=False):
        self.logger.info(f"Updating linter jobs={jobs} debug={debug}")
        try:
            report = self.linter.update(jobs, debug)
            self.changed |= len(report) > 0
            self.logger.info(f"{len(report)} files updated")
            self.return_result(self.update, 0, report=report)
        except Exception as e:
            #if __debug__: raise
            self.logger.exception("Exception thrown during update")
            self.return_result(self.update, 1, message=str(e))

    def make_report(self):
        self.logger.info("making report for all files")
        try:
            report = self.linter.make_report()
            self.logger.info(f"{len(report)} files in report")
            self.return_result(self.make_report, 0, report=report)
        except Exception as e:
            #if __debug__: raise
            self.logger.exception("Exception thrown during make_report")
            self.return_result(self.make_report, 1, message=str(e))

    @arg('path', help="Path to a tagger model")
    def load_tagger(self, path: str):
        self.logger.info(f'load_tagger from "{path}"')
        try:
            self.linter.load_tagger_model(path)
            self.return_result(self.load_tagger, 0, settings=self.linter.tagger.settings)
        except Exception as e:
            #if __debug__: raise
            self.logger.exception("Exception during load_tagger")
            self.return_result(self.load_tagger, 1, message=str(e))

    @arg('file', help="File used as root for the graph")
    def draw_graph(self, file: str):
        try:
            self.linter.import_graph.open_in_image_viewer(ModuleIdentifier.from_file(file))
            self.return_result(self.draw_graph, 0)
        except Exception as e:
            #if __debug__: raise
            self.logger.exception("Exception during draw_graph")
            self.return_result(self.draw_graph, 1, message=str(e))

    @arg('file', help="Path to current file")
    @arg('line', type=int, help="Line of the cursor")
    @arg('column', type=int, help="Column of the cursor")
    def goto_definition(self, file: str, line: int, column: int):
        self.logger.info(f'goto_definition "{file}" {line} {column}')
        try:
            definition = self.linter.goto_definition(file, line, column)
            self.return_result(self.goto_definition, 0, definition=definition)
        except Exception as e:
            #if __debug__: raise
            self.logger.exception("Exception during goto_definition")
            self.return_result(self.goto_definition, 1, message=str(e))

    @arg('file', help="Path to current file")
    @arg('line', type=int, help="Line of the cursor")
    @arg('column', type=int, help="Column of the cursor")
    def goto_implementation(self, file: str, line: int, column: int):
        self.logger.info(f'goto_implementation "{file}" {line} {column}')
        try:
            implementations = self.linter.goto_implementation(file, line, column)
            self.return_result(self.goto_implementation, 0, implementations=implementations)
        except Exception as e:
            #if __debug__: raise
            self.logger.exception("Exception during goto_implementation")
            self.return_result(self.goto_implementation, 1, message=str(e))

    @arg('file', help="Path to current file")
    @arg('line', type=int, help="Line of the cursor")
    @arg('column', type=int, help="Column of the cursor")
    def find_references(self, file: str, line: int, column: int):
        self.logger.info(f'find_references "{file}" {line} {column}')
        try:
            references = self.linter.find_references(file, line, column)
            self.return_result(self.find_references, 0, references=references)
        except Exception as e:
            #if __debug__: raise
            self.logger.exception("Exception during find_references")
            self.return_result(self.find_references, 1, message=str(e))

    @arg('file', help="Path to current file")
    @arg('context', type=int, help="Context that appears before the cursor")
    def auto_complete(self, file: str, context: str):
        self.logger.info(f'auto_complete "{file}" "{context}"')
        try:
            completion_items = self.linter.auto_complete(file, context)
            self.return_result(self.auto_complete, 0, completion_items=completion_items)
        except Exception as e:
            #if __debug__: raise
            self.logger.exception("Exception during auto_complete")
            self.return_result(self.auto_complete, 1, message=str(e))

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
            self.add,
            self.update,
            self.make_report,
            self.load_tagger,
            self.auto_complete,
            self.draw_graph,
            self.linter.ls,
            self.linter.modules,
            self.linter.symbols,
            self.linter.bindings,
            self.linter.trefis,
            self.linter.defis,
            *extra_commands
        ])

    def return_result(self, command, status, encoder=None, **kwargs):
        try:
            self.logger.info(f"Returning {command.__name__} with status {status}")
            return super().return_result(command, status, encoder=encoder or LinterJSONEncoder(), **kwargs)
        except Exception as e:
            #if __debug__: raise
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
        return obj.__dict__
        #raise Exception("Object is not serializable")


if __name__ == '__main__':
    @argh.arg('--root', help="Root dir")
    @argh.arg('--cache', help="Name of the file used as cache")
    def _main(root: str = None, cache: str = None):
        #if __debug__: sys.stdin = iter(())
        with Cache(cache, LinterCLI) as cache:
            cache.data.setup()
            if root:
                cache.data.add([[root]])
                cache.data.update()
            try:
                cache.data.run()
            finally:
                cache.write_on_exit = cache.write_on_exit and cache.data.changed
    argh.dispatch_command(_main)
