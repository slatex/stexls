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
from trefier.app.cli import CLI, CLIRestartException

__all__ = ['LinterCLI']

# set up logger by removing the default stderr sink
logger.remove()
# create log to file sink
logger.add(
    expanduser('~/.trefier/trefier.log'),
    enqueue=True,
    filter=lambda r: r['extra'].get('file', False))
# create log to stderr sink
logger.add(
    sys.stderr,
    enqueue=True,
    filter=lambda r: r['extra'].get('stream', False),
    format="{message}")

# make default logger for this module
logger = logger.bind(file=True, stream=False)

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
        print('showErrors', file=sys.stderr, flush=True)

    def __exit__(self, *args, **kwargs):
        print('hideErrors', file=sys.stderr, flush=True)


class LinterCLI(CLI):
    def __init__(self):
        super().__init__()
        self.linter = Linter()

    def __setstate__(self, state):
        self.linter = state

    def __getstate__(self):
        return self.linter

    def return_result(self, command: Callable, status: int, encoder: Optional[json.JSONEncoder] = None, **kwargs):
        """ Returns the result to stdout by parsing it with json. Every result is a json object on a single line
            with the guaranteed attributes "command" and "status". "command" is the name of the command and "status"
            is an integer indicating success with a value of 0. """
        try:
            logger.info(f"Returning {command.__name__} with status {status}")
            super().return_result(command, status, encoder=encoder or LinterJSONEncoder(), **kwargs)
        except Exception as e:
            logger.exception(f"Exception thrown during return_result of {command.__name__}")
            super().return_result(command, 1, message=str(e))

    def run(self, *extra_commands):
        logger.info(f"linter_cli.run with {len(extra_commands)} extra commands")
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
            self.catch_exception,
            self.execute,
            self.exit,
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
        logger.info(f"Adding directories")
        try:
            count_added = 0
            for globs in map(functools.partial(glob, recursive=True), directories):
                for directory in globs:
                    logger.info(f'Adding {directory}')
                    count_added += self.linter.add(directory)
            self.return_result(self.add, 0, message=f'Added {count_added} directories')
        except Exception as e:
            logger.exception("Exception during add_directory")
            self.return_result(self.add, 1, message=str(e))

    @arg('-a', '--force_report_all', help="If set, generates reports on all documents, even if unchanged.")
    @arg('-j', '--jobs', type=int, help="Number of jobs to help parsing tex files.")
    @arg('-m', '--use_multiprocessing', help="Enables multiprocessing")
    @arg('-d', '--debug', help="Enables debug mode")
    @arg('-p', '--progress', help="Enables some progress hints during update")
    def update(
        self,
        force_report_all: bool = False,
        jobs: int = None,
        use_multiprocessing: bool = True,
        progress: bool = True,
        debug: bool = False,):
        """ Updates the linter """
        logger.info(f"Updating linter jobs={jobs} use_multiprocessing={use_multiprocessing} debug={debug}")
        try:
            with ShowErrors(), Timer() as timer:
                report = self.linter.update(
                    force_report_all=force_report_all,
                    n_jobs=jobs,
                    use_multiprocessing=use_multiprocessing,
                    debug=debug,
                    silent=not progress)
            logger.info(f'Updated {len(report)} files in {round(timer.delta, 2) if timer.delta else "<undefined>"} seconds')
            self.return_result(self.update, 0, report=report)
        except Exception as e:
            logger.exception("Exception thrown during update")
            self.return_result(self.update, 1, message=str(e))

    @arg('path', help="Path to a tagger model")
    def load_tagger(self, path: str):
        """ Loads a *.model file and uses it to predict tags for files.
            Adding a tagger will enable the trefi hint functionality in the
            update report. """
        logger.info(f'load_tagger from "{path}"')
        try:
            with ShowErrors():
                self.linter.load_tagger_model(path)
            self.return_result(self.load_tagger, 0, settings=self.linter.tagger.settings)
        except Exception as e:
            logger.exception("Exception during load_tagger")
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
            logger.exception("Exception during draw_graph")
            self.return_result(self.draw_graph, 1, message=str(e))

    @arg('file', help="Path to current file")
    @arg('line', type=int, help="Line of the cursor")
    @arg('column', type=int, help="Column of the cursor")
    def goto_definition(self, file: str, line: int, column: int):
        """ Gathers definition information for the object at the specified location. """
        logger.info(f'goto_definition "{file}" {line} {column}')
        try:
            definition = self.linter.goto_definition(file, line, column)
            object_range = self.linter.get_object_range_at_position(file, line, column)
            self.return_result(self.goto_definition, 0, definition=definition, range=object_range)
        except Exception as e:
            logger.exception("Exception during goto_definition")
            self.return_result(self.goto_definition, 1, message=str(e))

    @arg('file', help="Path to current file")
    @arg('line', type=int, help="Line of the cursor")
    @arg('column', type=int, help="Column of the cursor")
    def goto_implementation(self, file: str, line: int, column: int):
        """ Gathers implementation details for the object at the specified location. """
        logger.info(f'goto_implementation "{file}" {line} {column}')
        try:
            implementations = self.linter.goto_implementation(file, line, column)
            object_range = self.linter.get_object_range_at_position(file, line, column)
            self.return_result(self.goto_implementation, 0, implementations=implementations, range=object_range)
        except Exception as e:
            logger.exception("Exception during goto_implementation")
            self.return_result(self.goto_implementation, 1, message=str(e))

    @arg('file', help="Path to current file")
    @arg('line', type=int, help="Line of the cursor")
    @arg('column', type=int, help="Column of the cursor")
    def find_references(self, file: str, line: int, column: int):
        """ Finds all references to the definition of the object at the location. """
        logger.info(f'find_references "{file}" {line} {column}')
        try:
            references = self.linter.find_references(file, line, column)
            self.return_result(self.find_references, 0, references=references)
        except Exception as e:
            logger.exception("Exception during find_references")
            self.return_result(self.find_references, 1, message=str(e))

    @arg('file', help="Path to current file")
    @arg('context', help="Context that appears before the cursor")
    def complete(self, file: str, context: str):
        """ Returns a list of possible autocompletions for the file given the context. """
        logger.info(f'complete "{file}" "{context}"')
        try:
            completion_items = list(self.linter.auto_complete(file, context))
            self.return_result(self.complete, 0, completion_items=completion_items)
        except Exception as e:
            logger.exception("Exception during complete")
            self.return_result(self.complete, 1, message=str(e))

    def raise_exception(self):
        """ Raises an exception. """
        raise Exception("raise_exception raised an exception!")

    def catch_exception(self):
        """ Raises an exception. """
        try:
            raise Exception("catch_exception raised an exception!")
        except Exception as e:
            logger.exception("test catch_exception caught")
            self.return_result(self.catch_exception, 1, message=str(e))

    def return_error_message(self):
        """ calls return_result with status 1 and a message. """
        self.return_result(self.return_error_message, 1, message="Error message returned!")
    
    @arg('source', help="Python source code to execute")
    def execute(self, source: str):
        logger.info(source)
        try:
            exec(source, globals(), locals())
        except:
            logger.exception('Exception in execute()')


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

return_restart_result: Optional[Callable[[], None]] = None

if __name__ == '__main__':
    @argh.arg('--cache', help="Name of the file used as cache.")
    @argh.arg('--tagger', type=str, help="Path to tagger model. Use None to disable tagging.")
    @argh.arg('--root', type=str, help="Path to initial root directory from which all **/source folders will be added to the workspace.")
    @argh.arg('-s', '--serialize', help="Enables output serialization in JSON format.")
    @argh.arg('-r', '--single_run', help="Launches in single run mode. Session will not be kept alive after loading the tagger, loading the cache, adding the root and then printing the diagnostic report.")
    def _main(cache: str = None, tagger: str = None, root: str = None, serialize: bool = False, single_run: bool = False):
        while True:
            with Cache(cache, LinterCLI) as c:
                c.data.set_output_serialization(serialize)

                @arg('--clear', help="If True, deletes the cache file before restarting the cli.")
                def restart(clear: bool = False):
                    """ Restarts the cli and optionally clears the cache before restart. """
                    try:
                        logger.bind(stream=False, file=True).info("Restarting" + (' with clearing cache' if clear else ''))
                        if clear:
                            c.write_on_exit = False
                            c.delete()
                        global return_restart_result
                        return_restart_result = lambda: c.data.return_result(restart, 0)
                    except Exception as e:
                        logger.bind(stream=True, file=False).error(str(e))
                        logger.bind(stream=False, file=True).exception("Exception before restart could be executed")
                        c.data.return_result(restart, 1)
                    c.data.restart()

                try:
                    if c.path:
                        logger.info(f'Using cachefile at {abspath(c.path)}')
                    else:
                        logger.info('No cachefile specified: No cache will be saved')
                    if tagger:
                        if not os.path.isfile(tagger):
                            raise Exception(f'Specified tagger "{tagger}" is not a file')
                        c.data.load_tagger(tagger)
                    if root:
                        if not os.path.isdir(root):
                            raise Exception(f'Specified root directory "{root}" is not a directory')
                        c.data.add(glob(os.path.join(root, '**/source'), recursive=True))
                    global return_restart_result
                    if return_restart_result is not None and callable(return_restart_result):
                        return_restart_result()
                        return_restart_result = None
                    if single_run:
                        logger.info('Running single-run update')
                        c.data.update(force_report_all=True)
                        return
                    else:
                        c.data.run(c.write, restart)
                except CLIRestartException:
                    logger.bind(file=True, stream=False).info("CLIRestartException received: continue execution...")
                    continue # restart by looping while(True) again
                except:
                    logger.exception("top-level exception in run()")
                    # disable write on any exception
                    c.write_on_exit = False
                finally:
                    c.write_on_exit = c.write_on_exit and c.data and c.data.linter and c.data.linter.changed
                if c.write_on_exit and c.path is not None:
                    logger.info(f'Ending session: Writing cache to "{c.path}"')
                else:
                    logger.info('Ending session: Without writing cache')
            break # break while(True)
    argh.dispatch_command(_main)
    #_main(None, None, '/home/marian/projects/trefier-backend/data/smglom/marian', True, True)