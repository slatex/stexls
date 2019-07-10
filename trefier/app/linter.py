from __future__  import annotations
from typing import List, Optional
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

from trefier.misc.location import Location, Range, Position
from trefier.linting.identifiers import ModuleIdentifier
from trefier.misc.Cache import Cache
from trefier.linting.linter import Linter
from trefier.app.cli import CLI

__all__ = ['LinterCLI']


def ignore_exceptions(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except:
            traceback.print_exc()

    return wrapper


class ShowErrors:
    """ Signals the wrapping extension that stderr should be interpreted as important information and should be
        somehow displayed for a better user experience. """
    def __enter__(self):
        print('showErrors', file=sys.stderr)

    def __exit__(self, *args, **kwargs):
        print('hideErrors', file=sys.stderr)


class LinterCLI(CLI):
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
    def update(self, jobs: int = None, use_multiprocessing: bool = True, debug: bool = False, progress: bool = True):
        """ Updates the linter """
        self.logger.info(f"Updating linter jobs={jobs} use_multiprocessing={use_multiprocessing} debug={debug}")
        try:
            with ShowErrors():
                report = self.linter.update(
                    jobs,
                    use_multiprocessing=use_multiprocessing,
                    debug=debug,
                    silent=not progress)
            self.logger.info(f"{len(report)} files updated")
            self.return_result(self.update, 0, report=report)
        except Exception as e:
            self.logger.exception("Exception thrown during update")
            self.return_result(self.update, 1, message=str(e))

    def make_report(self):
        """ Gathers all information and makes a report """
        self.logger.info("making report for all files")
        try:
            report = dict(self.linter.make_report())
            self.logger.info(f"{len(report)} files in report")
            self.return_result(self.make_report, 0, report=report)
        except Exception as e:
            self.logger.exception("Exception thrown during make_report")
            self.return_result(self.make_report, 1, message=str(e))

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

    @arg('module', type=ModuleIdentifier.from_id_string)
    @ignore_exceptions
    def transitive(self, module: ModuleIdentifier):
        yield from self.linter.import_graph.transitive.get(str(module), ())

    @arg('module', type=ModuleIdentifier.from_id_string)
    @ignore_exceptions
    def references(self, module: ModuleIdentifier):
        yield from self.linter.import_graph.references.get(str(module), ())

    @arg('module', type=ModuleIdentifier.from_id_string)
    @ignore_exceptions
    def parents(self, module: ModuleIdentifier):
        yield from self.linter.import_graph.parents_of(str(module), ())

    @arg('module', type=ModuleIdentifier.from_id_string)
    @ignore_exceptions
    def ls(self, module: ModuleIdentifier):
        yield from [
            d.file
            for d in self.linter._documents_in_module(str(module))
        ]

    @arg('module', type=ModuleIdentifier.from_id_string)
    @ignore_exceptions
    def exceptions(self, module: ModuleIdentifier):
        return {
            d.file: d.exceptions
            for d in self.linter._documents_in_module(str(module))
        }

    @arg('module', type=ModuleIdentifier.from_id_string)
    @ignore_exceptions
    def modules(self, module: ModuleIdentifier):
        return self.linter.import_graph.modules.get(str(module))

    @arg('module', type=ModuleIdentifier.from_id_string)
    @ignore_exceptions
    def imports(self, module: ModuleIdentifier):
        return self.linter.import_graph.graph.get(str(module))

    @arg('module', type=ModuleIdentifier.from_id_string)
    @ignore_exceptions
    def symbols(self, module: ModuleIdentifier):
        document = self.linter._map_module_identifier_to_module.get(str(module))
        if document:
            return document.module

    @arg('module', type=ModuleIdentifier.from_id_string)
    @ignore_exceptions
    def bindings(self, module: ModuleIdentifier):
        return [
            binding.binding
            for lang, binding
            in self.linter._map_module_identifier_to_bindings.get(str(module), {}).items()
        ]

    @arg('module', type=ModuleIdentifier.from_id_string)
    @ignore_exceptions
    def defis(self, module: ModuleIdentifier):
        for binding in self.linter._map_module_identifier_to_bindings.get(str(module), {}).values():
            yield from binding.defis

    @arg('module', type=ModuleIdentifier.from_id_string)
    @ignore_exceptions
    def trefis(self, module: ModuleIdentifier):
        for binding in self.linter._map_module_identifier_to_bindings.get(str(module), {}).values():
            yield from binding.trefis

    def setup(self):
        self._setup_called = True
        self.logger = logger.bind(name="linter_cli")
        self.logger.add(expanduser('~/.trefier/linter.log'), enqueue=True)
        self.logger.info("Session start")
        self.return_result(self.setup, 0)
    
    def status(self):
        return self.linter.tagger_path, self.linter.tagger, len(self.linter.tags)

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
            self.transitive,
            self.references,
            self.ls,
            self.exceptions,
            self.modules,
            self.imports,
            self.symbols,
            self.bindings,
            self.trefis,
            self.defis,
            self.status,
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
        self._setup_called = False
        self.linter = Linter()

    def __setstate__(self, state):
        self.logger = None
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
                    cache.data.logger.info(f'using cachefile at {abspath(cache.path)}')
                else:
                    cache.data.logger.info('no cachefile specified: No cache will be saved')
                if tagger:
                    assert os.path.isfile(tagger)
                    cache.data.load_tagger(tagger)
                if root:
                    assert os.path.isdir(root)
                    cache.data.add(glob(os.path.join(root, '**/source'), recursive=True))
                cache.data.run(cache.write)
            except:
                cache.write_on_exit = False
                cache.data.logger.exception("Exception during top-level run()")
                raise
            finally:
                try:
                    cache.write_on_exit = cache.write_on_exit and cache.data.linter.changed
                except:
                    cache.data.logger.exception('Exception during determining write_on_exit')
                    cache.write_on_exit = False
    argh.dispatch_command(_main)
