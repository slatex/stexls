
from cache import InstanceCache
from cli import *
from argh import *
import argparse
from database import *
from glob import glob
from os.path import abspath, join
from pathlib import Path
import itertools

_session_log = open(join(Path.home(), 'trefier_log.txt'), 'w+', encoding='utf-8')

def _log(*message):
    print(*message, file=_session_log,flush=True)

def _surround(value, default='', surround_open='"', surround_closed='"'):
    """ Surrounds if truthy, else returns empty string """
    if value:
        return f'{surround_open}{value}{surround_closed}'
    return default

class DatabaseCLI(CLI):
    def __init__(self):
        self.db = Database()
        _log('Database init')

    # override
    def return_result(self, command, status, **kwargs):
        """ Return result helper, that also logs the returned result. """
        result = super().return_result(command, status, **kwargs)
        _log(result)
        return result

    @arg('dirs', nargs=argparse.REMAINDER, type=lambda x: glob(x, recursive=True), help="List of directories to add to watched list.")
    @aliases('add')
    def add_directories(self, dirs):
        for dir in itertools.chain(*dirs):
            if isdir(dir):
                _log('Add dir:', dir)
                self.db.add_directory(dir)
            else:
                _log('Did not add:', dir)
    
    @arg('-j', '--jobs', type=int, help="Number of jobs to help parsing tex files.")
    @arg('-d', '--debug', help="Enables debug mode")
    def update(self, jobs=None, debug=False):
        _log(f'update jobs={jobs} debug={debug}')
        if self.db.update(jobs, debug):
            self.return_result(self.update, 0, message='"Files updated."')
        else:
            self.return_result(self.update, 0, message='"No files to update."')
    
    def ls(self):
        """ List all watched files. """
        return list(self.db._files)
    
    def modules(self):
        """ List all added modules. """
        return list(self.db._module_documents)

    @arg('file', type=str)
    @aliases('links')
    def provide_links(self, file):
        """ Provide links for a file. """
        links = [
            f'{{"range":{link.range.to_json()},"target":"{link.target}"}}'
            for link in self.db.provide_document_links(file)
        ]
        links = '[' + ','.join(links) + ']'
        self.return_result(self.provide_links, 0, links=links)
    
    @arg('file', type=str)
    @arg('line', type=int)
    @arg('column', type=int)
    @aliases('references')
    def find_references(self, file, line, column):
        _log('find-references', file, line, column)
        references = self.db.find_references(file, line, column)
        references = ','.join(map(Location.to_json, references))
        self.return_result(self.find_references, 0, targets=f'[{references}]')
    
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
        _log('goto-definition', file, line, column)
        definitions = self.db.goto_definition(file, line, column)
        targets = ','.join(map(lambda x: f'{{"range":{x[0].to_json()},"target":{x[1].to_json()}}}', definitions))
        self.return_result(self.goto_definition, 0, targets=f'[{targets}]')
    
    
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
        _log('auto-complete', file, context)
        try:
            items = (f'{{"label":"{label}","kind":"{kind}"}}' for label, kind in set(self.db.autocomplete(file, context)))
            items = '[' + ','.join(items) + ']'
            self.return_result(self.auto_complete, 0, items=items)
        except Exception as e:
            _log("Autocomplete Error:")
            _log(repr(e))
            self.return_result(self.auto_complete, 1, items=[], message=f'"{str(e)}"')

    @arg('-o', '--output', help="Optional path to where to store the image for later use.")
    @arg('-d', '--display', help="If True, directly renders the graph in the default or provided image viewer.")
    @arg('-v', '--viewer', help="Image viewer to use for display.")
    @arg('-m', '--module', help="Enables module input instead of a file")
    @arg('-t', '--temp', help="Writes to a tempfile instead of 'output'")
    @arg('file', type=str, help="Path to file.")
    @aliases('draw')
    def draw_graph(self, file, output=None, display=False, viewer=None, module=False, temp=False):
        """ Draws the import graph for a file and displays it in the specified image viewer or the default image viewer. """
        graph = self.db.import_graph(file, False, True)
        if graph:
            image_path = None
            if output or temp:
                if temp:
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as file:
                        image_path = graph.write_image(file.name)
                else:
                    image_path = graph.write_image(output)
            if display:
                image_path = graph.open_in_image_viewer(image_path or output, image_viewer=viewer)
            if image_path:
                self.return_result(self.draw_graph, 0, image=_surround(image_path))
            else:
                self.return_result(self.draw_graph, 1, message='"No image created."')
        else:
            self.return_result(self.draw_graph, 1, message='"No graph created."')

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
        _log('optimize:', file)
        self.update(jobs=jobs)
        graph = self.db.import_graph(file, False, True)
        missing_imports = '[' + ','.join(f'{{"location":{location.to_json()},"symbol":"{symbol}"}}' for location, symbol in self.db.find_missing_imports(file)) + ']'
        unresolved_symbols = '[' + ','.join(f'{{"location":{location.to_json()},"symbol":"{symbol}"}}' for location, symbol in self.db.find_unresolved_symbols(file)) + ']'
        other = '[' + ','.join(map(lambda x: x.json, self.db.errors)) + ']'
        self.return_result(self.optimize, 0, graph=graph.json if graph else '{}', missing_imports=missing_imports, unresolved_symbols=unresolved_symbols, other=other)

    def run(self, dirs, jobs=4, *extra_commands):
        """ Runs cli.
        Arguments:
            :param dirs: List of glob patterns from which to draw database source directories.
            :param jobs: Number of jobs to use for parsing tex files.
        """
        super().run([
            self.add_directories,
            self.update,
            self.optimize,
            self.auto_complete,
            self.find_references,
            self.goto_definition,
            self.provide_links,
            self.ls,
            self.modules,
            self.draw_graph,
            *extra_commands
        ], initial_command_list=['add-directories ' + ' '.join(itertools.chain(*dirs)), f'update -j{jobs}'])
