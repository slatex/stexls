
from argh import *
import argparse
from glob import glob
from os.path import abspath, join, isdir, expanduser
from pathlib import Path
import itertools
import tempfile

from loguru import logger

from ..misc import Cache
from ..database import Database, DatabaseJSONEncoder
from .cli import CLI

__all__ = ['DatabaseCLI']

class DatabaseCLI(CLI):
    def __init__(self):
        super().__init__()
        self.db = Database()
        self.logger = None
    
    def return_result(self, command, status, encoder=None, **kwargs):
        self.logger.info(f"Returning {command.__name__} with status {status}")
        return super().return_result(command, status, encoder=encoder or DatabaseJSONEncoder(), **kwargs)

    @arg('dirs', nargs=argparse.REMAINDER, type=lambda x: glob(x, recursive=True), help="List of directories to add to watched list.")
    @aliases('add')
    def add_directories(self, dirs):
        self.logger.info(f"Adding directories")
        added = 0
        rejected = 0
        for dir in itertools.chain(*dirs):
            if isdir(dir):
                added += 1
                self.logger.info(f"Adding {dir}")
                self.db.add_directory(dir)
            else:
                self.logger.info(f"Rejecting {dir}")
                rejected += 1
        self.return_result(self.add_directories, 0, message=f'Added {added} directories and rejected {rejected} non-directories.')
    
    @arg('-j', '--jobs', type=int, help="Number of jobs to help parsing tex files.")
    @arg('-d', '--debug', help="Enables debug mode")
    def update(self, jobs=None, debug=False):
        self.logger.info(f"Updating databse jobs={jobs} debug={debug}")
        if self.db.update(jobs, debug):
            self.logger.info(f"Some files changed")
            self.changed = True
            self.return_result(self.update, 0, message='Files updated')
        else:
            self.logger.info(f"No files changed")
            self.return_result(self.update, 0, message='No files to update')
    
    def ls(self):
        """ List all watched files. """
        return list(self.db._files)
    
    def modules(self):
        """ List all added modules. """
        return [{path: doc.module} for path, doc in self.db._module_documents.items()]

    @arg('file', type=str)
    @arg('line', type=int)
    @arg('column', type=int)
    @aliases('references')
    def find_references(self, file, line, column):
        self.logger.info(f"Finding references at {abspath(file)}:{line}:{column}")
        references = self.db.find_references(file, line, column)
        self.logger.info(f"Found {len(references)} references")
        self.return_result(self.find_references, 0, targets=references)
    
    @arg('file', type=str)
    @arg('line', type=int)
    @arg('column', type=int)
    @aliases('goto')
    def goto_definition(self, file, line, column):
        """ Returns a list of definitions each containing
            {
                range: Range of defined symbol,
                target: {
                    file: File of definition,
                    range: Range of definition in file
                }
            }
        """
        try:
            self.logger.info(f"goto definition of object at {abspath(file)}:{line}:{column}")
            definitions = list(self.db.goto_definition(file, line, column))
            self.logger.info(f"Found {len(definitions)} definitions")
            targets = [{"range":range, "target":target} for range, target in definitions]
            self.return_result(self.goto_definition, 0, targets=targets, message=f'{len(definitions)} definitions found at {file}:{line}:{column}.')
        except Exception as e:
            self.logger.exception("Exception during goto_definition()")
            self.return_result(self.goto_definition, 1, message=str(e))
    
    @arg('file', type=str, help="File the context is from.")
    @arg('context', type=str, help="Context that you want to complete.")
    @aliases('complete')
    def auto_complete(self, file, context):
        """
            Proposes labels that complete the given context inside the file.
            returns [
                {label: string, kind: string},
                ...
            ]
        """
        try:
            self.logger.info(f"autocomplete {abspath(file)} with context=\"{context}\"")
            items = [{"label":label,"kind":kind} for label, kind in set(self.db.autocomplete(file, context))]
            self.logger.info(f"providing {len(items)} auto-complete items")
            self.return_result(self.auto_complete, 0, items=items, message=f'{len(items)} autocompletions displayed.')
        except Exception as e:
            self.logger.exception("Failed to create autocompletions")
            self.return_result(self.auto_complete, 1, message=str(e))

    @arg('-o', '--output', help="Optional path to where to store the image for later use.")
    @arg('-d', '--display', help="If True, directly renders the graph in the default or provided image viewer.")
    @arg('-v', '--viewer', help="Image viewer to use for display.")
    @arg('-t', '--temp', help="Writes to a tempfile instead of 'output'")
    @arg('file', type=str, help="Path to file.")
    @aliases('draw')
    def draw_graph(self, file, output=None, display=False, viewer=None, temp=False):
        """ Draws the import graph for a file and displays it in the specified image viewer or the default image viewer. """
        self.logger.info(f"Generating import graph for file or module {file}")
        graph = self.db.import_graph(file, False, True)
        self.logger.info("Import graph generated: %s" % ("No", "Yes")[graph is None])
        if graph:
            image_path = None
            if output or temp:
                if temp:
                    self.logger.info("Writing image to tempfile")
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as file:
                        image_path = graph.write_image(file.name)
                else:
                    image_path = graph.write_image(output)
                self.logger.info(f"Written image to {image_path}")
            if display:
                self.logger.info(f"Displaying image at {image_path} using {viewer or 'the default image viewer'}")
                image_path = graph.open_in_image_viewer(image_path, image_viewer=viewer)
            if image_path:
                self.return_result(self.draw_graph, 0, image=image_path)
            else:
                self.logger.error("No image generated")
                self.return_result(self.draw_graph, 1, message='No image created.')
        else:
            self.return_result(self.draw_graph, 1, message='Provided file argument does not have a module.')

    @arg('file')
    @arg('-j', '--jobs', type=int, help="Update database using helper threads.")
    def optimize(self, file, jobs=None):
        """ Finds errors with the file.
        Returns object {
            command: str,
            status: number,
            graph: {
                reimports: [ {
                    source_module: str,
                    target_module: str,
                    location: Location,
                    reasons: [ Location... ]
                }],
                cycles: [{
                    location: Location, # location of import
                    target: string # module that is imported
                }],
                failed: [{
                    location: Location,
                    module: str
                }]
            },
            missing_imports: [
                {location: Location, symbol: str}
            ],
            unresolved_symbols: [
                {location: Location, symbol: str}
            ],
            other: [
                {
                    type: ExceptionType identifier,
                    ... type specific arguments
                }
            ]
        }
        """
        try:
            self.logger.info(f"Optimizing {abspath(file)}")
            self.update(jobs=jobs)
            import json
            graph = self.db.import_graph(file, False, True)
            self.logger.info("Import graph generated: %s" % ("No", "Yes")[graph is None])
            missing_imports = [{"location":location,"symbol":symbol} for location, symbol in self.db.find_missing_imports(file)]
            unresolved_symbols = [{"location":location,"symbol":symbol} for location, symbol in self.db.find_unresolved_symbols(file)]
            other = [ json.loads(x.json) for x in self.db.errors ]
            self.logger.info(f"{len(missing_imports)} missing imports")
            self.logger.info(f"{len(unresolved_symbols)} unresolved symbols")
            self.logger.info(f"{len(other)} other optimizations")
            self.return_result(self.optimize, 0, graph=graph, missing_imports=missing_imports, unresolved_symbols=unresolved_symbols, other=other)
        except Exception as e:
            self.logger.exception("Exception during optimize()")
            self.return_result(self.optimize, 1, message=str(e))
        
    def setup(self):
        self.changed = False
        self.logger = logger.bind(name="model_cli")
        self.logger.add(expanduser('~/.trefier/database_cli.log'), enqueue=True)
        self.logger.info("Beginning session")
        self.return_result(self.setup, 0)

    def run(self, *extra_commands):
        self.logger.info(f"Running with {len(extra_commands)} extra commands")
        self.setup()
        super().run([
            self.add_directories,
            self.update,
            self.optimize,
            self.auto_complete,
            self.find_references,
            self.goto_definition,
            self.ls,
            self.modules,
            self.draw_graph,
            *extra_commands
        ])
