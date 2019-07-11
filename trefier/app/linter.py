from __future__  import annotations
from typing import List, Optional, Callable
from argh import arg, aliases, dispatch_command
import argparse
from glob import glob
from os.path import isdir, expanduser, abspath
import itertools
import os
import sys
from loguru import logger
import argh
import traceback
import functools
import json
import time

from trefier.misc.location import Location, Range, Position
from trefier.linting.identifiers import ModuleIdentifier
from trefier.misc.Cache import Cache
from trefier.linting.linter import Linter
from trefier.app.cli import CLI

__all__ = ['LinterCLI']


class Timer:
    def __init__(self):
        self.begin = None
        self.delta = None

    def __enter__(self):
        self.begin = time.time()
        return self
    
    def __exit__(self, *args, **kwargs):
        self.delta = time.time() - self.begin


class ShowErrors:
    """ By writing "showErrors" to stderr it signals the wrapping extension
        that stderr should be interpreted as important information and should be
        somehow displayed for a better user experience.
        "hideErrors" signals that the anything after that can be ignored. """
    def __enter__(self):
        print('showErrors', file=sys.stderr)

    def __exit__(self, *args, **kwargs):
        print('hideErrors', file=sys.stderr)


class LinterCLI(CLI):
    def __init__(self):
        super().__init__()
        self.logger = None
        self._setup_called = False
        self.linter = Linter()

    def __setstate__(self, state):
        self.logger = None
        self._setup_called = False
        self.linter = state

    def __getstate__(self):
        return self.linter

    def return_result(self, command: Callable, status: int, encoder: Optional[json.JSONEncoder] = None, **kwargs):
        """ Returns the result to stdout by parsing it with json. Every result is a json object on a single line
            with the guaranteed attributes "command" and "status". "command" is the name of the command and "status"
            is an integer indicating success with a value of 0. """
        try:
            self.logger.info(f"Returning {command.__name__} with status {status}")
            return super().return_result(command, status, encoder=encoder or LinterJSONEncoder(), **kwargs)
        except Exception as e:
            self.logger.exception(f"Exception thrown during return_result of {command.__name__}")
            super().return_result(command, 1, message=str(e))

    def setup(self):
        """ Initializes the linter. Must first be called before doing anything. """
        try:
            if self._setup_called:
                self.return_result(self.setup, 1, message="setup already called")
            else:
                self.logger = logger.bind(name="linter_cli")
                self.logger.add(expanduser('~/.trefier/linter.log'), enqueue=True)
                self.logger.info("Session start")
                self._setup_called = True
                self.return_result(self.setup, 0)
        except Exception as e:
            self.return_result(self.setup, 1, message=str(e))

    def run(self, *extra_commands):
        if not self._setup_called:
            raise Exception("linter_cli.setup() must be called before running")
        self.logger.info(f"linter_cli.run with {len(extra_commands)} extra commands")
        super().run([
            self.add,
            self.update,
            self.goto_definition,
            self.goto_implementation,
            self.find_references,
            self.load_tagger,
            self.complete,
            self.draw_graph,
            self.return_error_message,
            self.raise_exception,
            *extra_commands
        ])

    @arg('directories',
         nargs=argparse.REMAINDER,
         type=str,
         help="List of directories to add to watched list.")
    def add(self, directories: List[os.PathLike]):
        """ Adds a list of directories to the watched directory list.
            All .tex files inside these added directories will be
            automatically detected and scanned by the linter. """
        self.logger.info(f"Adding directories")
        try:
            count_added = 0
            for globs in map(functools.partial(glob, recursive=True), directories):
                for directory in globs:
                    self.logger.info(f'Adding {directory}')
                    count_added += self.linter.add(directory)
            self.return_result(self.add, 0, message=f'Added {count_added} directories')
        except Exception as e:
            self.logger.exception("Exception during add_directory")
            self.return_result(self.add, 1, message=str(e))

    @arg('-j', '--jobs', type=int, help="Number of jobs to help parsing tex files.")
    @arg('-m', '--use_multiprocessing', help="Enables multiprocessing")
    @arg('-d', '--debug', help="Enables debug mode")
    @arg('-p', '--progress', help="Enables some progress hints during update")
    def update(self,
               jobs: int = None,
               use_multiprocessing: bool = True,
               progress: bool = True,
               debug: bool = False,):
        """ Updates the linter """
        self.logger.info(f"Updating linter jobs={jobs} use_multiprocessing={use_multiprocessing} debug={debug}")
        try:
            with ShowErrors(), Timer() as timer:
                report = self.linter.update(
                    n_jobs=jobs,
                    use_multiprocessing=use_multiprocessing,
                    debug=debug,
                    silent=not progress)
            self.logger.info(f'Update done in {round(timer.delta, 2) if timer.delta else "<undefined>"} seconds')
            self.logger.info(f"{len(report)} files updated")
            self.return_result(self.update, 0, report=report)
        except Exception as e:
            self.logger.exception("Exception thrown during update")
            self.return_result(self.update, 1, message=str(e))

    @arg('path', help="Path to a tagger model")
    def load_tagger(self, path: str):
        """ Loads a *.model file and uses it to predict tags for files.
            Adding a tagger will enable the trefi hint functionality in the
            update report. """
        self.logger.info(f'load_tagger from "{path}"')
        try:
            with ShowErrors():
                self.linter.load_tagger_model(path)
            self.return_result(self.load_tagger, 0, settings=self.linter.tagger.settings)
        except Exception as e:
            self.logger.exception("Exception during load_tagger")
            self.return_result(self.load_tagger, 1, message=str(e))

    @arg('file', help="File used as root for the graph")
    @arg('--image_viewer', help="Name of the programm you want to open the graph image with or None for default")
    def draw_graph(self, file: str, image_viewer: Optional[str] = None):
        """ Simply creates the import graph of the provided file and displays it with
            the specified image viewer or the default for your OS. """
        try:
            self.linter.import_graph.open_in_image_viewer(ModuleIdentifier.from_file(file), image_viewer=image_viewer)
            self.return_result(self.draw_graph, 0)
        except Exception as e:
            self.logger.exception("Exception during draw_graph")
            self.return_result(self.draw_graph, 1, message=str(e))

    @arg('file', help="Path to current file")
    @arg('line', type=int, help="Line of the cursor")
    @arg('column', type=int, help="Column of the cursor")
    def goto_definition(self, file: str, line: int, column: int):
        """ Gathers definition information for the object at the specified location. """
        self.logger.info(f'goto_definition "{file}" {line} {column}')
        try:
            definition = self.linter.goto_definition(file, line, column)
            object_range = self.linter.get_object_range_at_position(file, line, column)
            self.return_result(self.goto_definition, 0, definition=definition, range=object_range)
        except Exception as e:
            self.logger.exception("Exception during goto_definition")
            self.return_result(self.goto_definition, 1, message=str(e))

    @arg('file', help="Path to current file")
    @arg('line', type=int, help="Line of the cursor")
    @arg('column', type=int, help="Column of the cursor")
    def goto_implementation(self, file: str, line: int, column: int):
        """ Gathers implementation details for the object at the specified location. """
        self.logger.info(f'goto_implementation "{file}" {line} {column}')
        try:
            implementations = self.linter.goto_implementation(file, line, column)
            object_range = self.linter.get_object_range_at_position(file, line, column)
            self.return_result(self.goto_implementation, 0, implementations=implementations, range=object_range)
        except Exception as e:
            self.logger.exception("Exception during goto_implementation")
            self.return_result(self.goto_implementation, 1, message=str(e))

    @arg('file', help="Path to current file")
    @arg('line', type=int, help="Line of the cursor")
    @arg('column', type=int, help="Column of the cursor")
    def find_references(self, file: str, line: int, column: int):
        """ Finds all references to the definition of the object at the location. """
        self.logger.info(f'find_references "{file}" {line} {column}')
        try:
            references = self.linter.find_references(file, line, column)
            self.return_result(self.find_references, 0, references=references)
        except Exception as e:
            self.logger.exception("Exception during find_references")
            self.return_result(self.find_references, 1, message=str(e))

    @arg('file', help="Path to current file")
    @arg('context', help="Context that appears before the cursor")
    def complete(self, file: str, context: str):
        """ Returns a list of possible autocompletions for the file given the context. """
        self.logger.info(f'complete "{file}" "{context}"')
        try:
            completion_items = list(self.linter.auto_complete(file, context))
            self.return_result(self.complete, 0, completion_items=completion_items)
        except Exception as e:
            self.logger.exception("Exception during complete")
            self.return_result(self.complete, 1, message=str(e))
    
    def raise_exception(self):
        """ Raises an exception. """
        raise Exception("raise_exception raised an exception!")

    def return_error_message(self):
        """ calls return_result with status 1 and a message. """
        self.return_result(self.return_error_message, 1, message="Error message returned!")


class LinterJSONEncoder(json.JSONEncoder):
    def default(self, obj):  # pylint: disable=E0202
        if isinstance(obj, Position):
            return {"line": obj.line, "column": obj.column}
        if isinstance(obj, Range):
            return {"begin": obj.begin, "end": obj.end}
        if isinstance(obj, Location):
            return {"file": obj.file, "range": obj.range}
        if isinstance(obj, ModuleIdentifier):
            return str(obj)
        return obj.__dict__


if __name__ == '__main__':
    @argh.arg('--cache', help="Name of the file used as cache")
    @argh.arg('--tagger', type=str, help="Path to tagger model")
    @argh.arg('--root', type=str, help="Root dir")
    def _main(cache: str = None, tagger: str = None, root: str = None):
        with Cache(cache, LinterCLI) as cache:
            try:
                cache.data.setup()
                if cache.path:
                    cache.data.logger.info(f'Using cachefile at {abspath(cache.path)}')
                else:
                    cache.data.logger.info('No cachefile specified: No cache will be saved')
                if tagger:
                    assert os.path.isfile(tagger)
                    cache.data.load_tagger(tagger)
                if root:
                    assert os.path.isdir(root)
                    cache.data.add(glob(os.path.join(root, '**/source'), recursive=True))
                cache.data.run(cache.write)
            except:
                cache.data.logger.exception("Exception during top-level run()")
                # disable write on any exception
                cache.write_on_exit = False
            finally:
                if cache.data and cache.data.linter:
                    # only save if data.linter exists and linter is marked as changed
                    cache.write_on_exit = cache.write_on_exit and cache.data.linter.changed
                else:
                    # else do not save
                    cache.write_on_exit = False
            if cache.write_on_exit:
                cache.data.logger.info(f'Ending session: Writing cache to "{cache.path}"')
            else:
                cache.data.logger.info('Ending session: Without writing cache')
    argh.dispatch_command(_main)
