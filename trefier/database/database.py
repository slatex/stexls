import multiprocessing
from glob import glob
from os.path import abspath, isdir, isfile, join, relpath, dirname
import itertools
from collections import defaultdict
import re
import tempfile
import pydot
import numpy as np
from PIL import Image
from io import StringIO
import sys
import subprocess
from types import SimpleNamespace

from ..tokenization import TexDocument
from .location import Location, Range, Position
from .file_watcher import FileWatcher


class DatabaseException(BaseException):
    pass


class DatabaseFileException(DatabaseException):
    """ Exception that receives a file as argument. """
    def __init__(self, message, file):
        super().__init__(message)
        self.message = message
        self.file = file
    
    @property
    def json(self):
        return f'{{"type":"DatabaseFileException","file":"{self.file}","message":"{self.message}"}}'
    
    def __reduce__(self):
        return type(self), (self.file,)


class NotInASourceDirectoryException(DatabaseFileException):
    def __init__(self, file):
        super().__init__("'%s' is not located in a 'source' directory" % file, file)


class MissingHeaderException(DatabaseFileException):
    def __init__(self, file):
        super().__init__("'%s' does neither have a modsig nor a mhmodnl header." % file, file)


class InvalidHeaderException(DatabaseFileException):
    def __init__(self, file):
        super().__init__("'%s' does have modsig AND mhmodnl defined." % file, file)


class TooManyModulesInFileException(DatabaseFileException):
    def __init__(self, file):
        super().__init__("'%s' contains more than one module." % file, file)


class TooManyBindingsInFileException(DatabaseFileException):
    def __init__(self, file):
        super().__init__("'%s' has more than one binding defined." % file, file)


class CircularDependencyException(DatabaseException):
    def __init__(self, source, target, context):
        super().__init__(f"Cycle created by importing {target} from {source}: {context}")
        self.source = source
        self.target = target
        self.context = context
    
    def __reduce__(self):
        return type(self), (self.source, self.target, self.context)
    
    @property
    def json(self):
        raise RuntimeError("CircularDependency should not be jsonfied.")


class DuplicateImportException(DatabaseException):
    def __init__(self, location, duplicate_module_name, previous_location):
        super().__init__(f"Duplicate definition of '{duplicate_module_name}'. Previously defined here: '{previous_location}'")
        self.location = location
        self.duplicate_module_name = duplicate_module_name
        self.previous_location = previous_location
    
    def __reduce__(self):
        return type(self), (self.location, self.duplicate_module_name, self.previous_location)
    
    @property
    def json(self):
        return f'{{"type":"DuplicateImportException","location":{self.location.to_json()},"target":"{self.duplicate_module_name}","previous_location":{self.previous_location.to_json()}}}'


class InvalidNumberSymbolArgumentsException(DatabaseException):
    def __init__(self, location, received, required):
        super().__init__(f'{location} Expected at least {required} arguments but received {received}.')
        self.location = location
        self.received = received
        self.required = required
    
    def __reduce__(self):
        return type(self), (self.location, self.received, self.required)
    
    @property
    def json(self):
        return f'{{"type":"InvalidNumberSymbolArgumentsException","location":{self.location.to_json()},"received":{self.received},"expected":{self.required}}}'


class GenericSymbol(Location):
    """ Simply records the location and content of the symbol. """
    def __init__(self, file:str, oarg_range:Range, range:Range, offset:tuple, environment:str, tokens):
        super().__init__(file, range, offset)
        self.oarg_range = oarg_range
        self.environment = environment
        self.tokens = tokens
    
    @staticmethod
    def create(document, pattern):
        for tokens, begin_offset, env in document.find_all(pattern, return_position=True, pattern=True, return_env_name=True):
            if not tokens:
                continue
            begin_position = Position(*document.offset_to_position(begin_offset))
            end_offset = tokens[-1].end
            end_position = Position(*document.offset_to_position(end_offset+1))
            oarg_ranges = [_token_to_range(document, t) for t in tokens if 'OArg' in t.envs]
            oarg_range = Range(oarg_ranges[0].begin, oarg_ranges[-1].end) if oarg_ranges else None
            yield GenericSymbol(
                document.file,
                oarg_range,
                Range(begin_position, end_position),
                (begin_offset, end_offset), env, tokens)
    
    def __iter__(self):
        return iter(self.tokens)
    
    @property
    def lexemes(self):
        return tuple(sub.lexeme for token in self for sub in token.subtokens())

    @property
    def oargs(self):
        return tuple(token.lexeme for token in self if 'OArg' in token.envs)

    @property
    def rargs(self):
        return tuple(token.lexeme for token in self if 'RArg' in token.envs)
    
    @property
    def token_ranges(self):
        return [
            Range(Position(*token.document.offset_to_position(token.begin)), Position(*token.document.offset_to_position(token.end)))
            for token in self
            if 'RArg' in token.envs
        ]

class ModuleFile(Location):
    def __init__(self, file, range, offset):
        super().__init__(file, range, offset)
        file = abspath(file)
        self._dirs = None
        self._source = None
        self._dirs = file.split('/')
        if 'source' not in self._dirs:
            raise NotInASourceDirectoryException(file)
        self._source = len(self._dirs) - 1 - self._dirs[::-1].index('source') # in order to prevent paths that have multiple 'source' directories
    
    @property
    def base_directory(self):
        return '/'.join(self._dirs[:self._source-2])

    @property
    def repository(self):
        return '/'.join(self._dirs[:self._source][-2:])
    
    @property
    def module(self):
        return join('/'.join(self._dirs[self._source+1:-1]), self._dirs[-1].split('.')[0])

    @property
    def identifier(self):
        return join(self.repository, self.module)

    def __repr__(self):
        return self.identifier
    
    def __eq__(self, that):
        if not isinstance(that, ModuleFile):
            return False
        return self.identifier == that.identifier
    
    def __neq__(self, that):
        return not (self == that)
    
    def __hash__(self):
        return hash(repr(self))

def _token_to_range(document, token):
    return Range(
        Position(*document.offset_to_position(token.begin)),
        Position(*document.offset_to_position(token.end)))

class ModuleSignature(ModuleFile):
    dummy = SimpleNamespace(imports=(), errors=(), name=None, file=None)

    def __init__(self, document, name):
        super().__init__(document.file, _token_to_range(document, name), (name.begin, name.end))
        self.name = name.lexeme

        #syms = list(GenericSymbol.create(document, '''symi+'''))

        self.imports, self.errors = self._parse_imports(document)
    
    def _parse_imports(self, document):
        """ Parses and returns import map and errors from a document. """
        imports = dict()
        errors = []
        for gimport in list(GenericSymbol.create(document, '''gimport\\*?''')):
            target_identifier = self._get_target_module_identifier(gimport)
            if target_identifier in imports:
                errors.append(DuplicateImportException(gimport, target_identifier, imports[target_identifier]))
            else:
                imports[target_identifier] = gimport
        return imports, errors
    
    def _get_target_module_identifier(self, gimport):
        """ Parses a raw gimport statement into an import """
        from_repository = ''.join(gimport.oargs) if gimport.oargs else self.repository
        target_module_name = '/'.join(gimport.rargs)
        target_module_identifier = join(from_repository, target_module_name)
        return target_module_identifier
    
    # def __getitem__(self, module:str):
    #     return self.imports.get(module)

class LanguageBinding(ModuleFile):
    dummy = SimpleNamespace(defis=(), trefis=(), errors=(), lang=None, bound_module=None, file=None)

    def __init__(self, document, module, lang):
        super().__init__(document.file, _token_to_range(document, module), (module.begin, module.end))
        self.bound_module = module.lexeme
        self.lang = lang.lexeme
        self.defis, self.trefis, self.errors = self._parse_binding(document)
    
    def _parse_binding(self, document):
        defis, errors1 = self._parse_symbols(document, GenericSymbol.create(document, '''[ma]?defi+s?'''))
        trefis, errors2 = self._parse_symbols(document, GenericSymbol.create(document, '''[ma]?trefi+s?'''))
        return defis, trefis, errors1 + errors2
    
    def _parse_symbols(self, document, generic_symbols):
        parsed = []
        errors = []
        for symbol in generic_symbols:
            if len(symbol.rargs) < 1:
                errors.append(InvalidNumberSymbolArgumentsException(symbol, len(symbol.rargs), 1))
                continue
            if re.fullmatch(r'm?am?(tr|d)efi+s?', symbol.environment):
                if len(symbol.rargs) < 2:
                    errors.append(InvalidNumberSymbolArgumentsException(symbol, len(symbol.rargs), 2))
                    continue
                # main symbol
                parsed.append(SubSymbol(
                    symbol, symbol.rargs[1:],
                    Range(symbol.token_ranges[1:][0].begin, symbol.token_ranges[1:][-1].end)))
                # alt
                parsed.append(SubSymbol(
                    symbol, symbol.rargs[:1],
                    Range(symbol.token_ranges[:1][0].begin, symbol.token_ranges[:1][-1].end)))
            else:
                parsed.append(SubSymbol(
                    symbol, symbol.rargs,
                    Range(symbol.token_ranges[0].begin, symbol.token_ranges[-1].end)))
        return parsed, errors
    
    def __repr__(self):
        return f"(Binding module={self.identifier} lang={self.lang})"

class DatabaseDocument(TexDocument):
    dummy = SimpleNamespace(binding=LanguageBinding.dummy, module=ModuleSignature.dummy)

    def __init__(self, document_or_path):
        super().__init__(document_or_path)
        self.module = None
        self.binding = None
        self._errors = []

        # can't throw exceptions because of multiprocessing

        if not self.success:
            return

        # turn success off until the end
        self.success = False

        if not (self.find_all('mhmodnl') or self.find_all('modsig')):
            self._errors.append(MissingHeaderException(self.file))
            return

        if self.find_all('mhmodnl') and self.find_all('modsig'):
            self._errors.append(InvalidHeaderException(self.file))
            return

        for env in self.find_all('modsig'):
            if self.module:
                self._errors.append(TooManyModulesInFileException(file))
                return
            try:
                self.module = ModuleSignature(
                    document = self,
                    **dict(zip(('name',), (x for x in env if 'RArg' in x.envs))))
            except DatabaseException as e:
                self._errors.append(e)
                return
        
        for env in self.find_all('mhmodnl'):
            if self.binding:
                self._errors.append(TooManyBindingsInFileException(file))
                return
            try:
                self.binding = LanguageBinding(
                    document = self,
                    **dict(zip(('module', 'lang'), (x for x in env if 'RArg' in x.envs))))
            except DatabaseException as e:
                self._errors.append(e)
                return
        
        self.success = True #len(self.exception) == 0
    
    @property
    def errors(self):
        return self._errors + (self.binding or self.module).errors
    
    @property
    def repository(self):
        if self.module:
            return self.module.repository
        elif self.binding:
            return self.binding.repository
    
    @property
    def module_name(self):
        if self.module:
            return self.module.name
        elif self.binding:
            return self.binding.bound_module
        
    @property
    def module_identifier(self):
        if self.module:
            return self.module.identifier
        elif self.binding:
            return self.binding.identifier
    
class SubSymbol:
    def __init__(self, symbol, tokens, discovery_range):
        self.symbol = symbol
        self.tokens = tokens
        self.range = discovery_range

    def contains(self, position):
        """ True if the position is above any token of the sub symbol. """
        return self.range.contains(position)

    @property
    def name(self):
        """ property of defis: \\defi[name=<name>]{...} """
        if self.symbol.oargs and self.symbol.oargs[0].startswith('name='):
            return self.symbol.oargs[0][len('name='):]
        return None
    
    @property
    def target_module(self):
        """ trefi property: \\trefi[target_module?...]{...} """
        if self.symbol.oargs:
            args = self.symbol.oargs[0].split('?')
            if args[0]:
                # only return target module if it is not empty in case of \trefi[?symbol]{...}
                return args[0]
        return None
    
    @property
    def target_module_range(self):
        """ Returns the range for the module part in oargs if target_module is defined. Else returns the oarg range again. """
        tm = self.target_module
        if tm:
            return Range(self.symbol.oarg_range.begin, Position(self.symbol.oarg_range.begin.line, self.symbol.oarg_range.begin.column + len(tm)))
        return self.symbol.oarg_range

    @property
    def target_symbol(self):
        """ trefi property: \trefi[...?target_symbol]{...} """
        if self.symbol.oargs:
            args = self.symbol.oargs[0].split('?')
            if len(args) > 1:
                return args[1]
        return None
    
    @property
    def target_symbol_range(self):
        """ Returns the range for the symbol part in oargs if target_symbol is defined. Else returns the oarg range again. """
        ts = self.target_symbol
        if ts:
            return Range(Position(self.symbol.oarg_range.end.line, self.symbol.oarg_range.end.column - len(ts)), self.symbol.oarg_range.end)
        return self.symbol.oarg_range

    def __repr__(self):
        return repr(self.symbol) + ' ' + repr(self.tokens)

import json

class DatabaseJSONEncoder(json.JSONEncoder):
    def default(self, obj):  # pylint: disable=E0202
        if isinstance(obj, Position):
            return {"line":obj.line, "column": obj.column}
        if isinstance(obj, Range):
            return {"begin":obj.begin, "end": obj.end}
        if isinstance(obj, Location):
            return {"file": obj.file, "range": obj.range}
        if isinstance(obj, SubSymbol):
            return obj.symbol
        if isinstance(obj, ImportGraph):
            return {
                "failed": [
                    {"location": location, "module": module}
                    for location, module
                    in obj.failed_to_import.items()
                ],
                "reimports": [
                    {
                        "location": obj.graph[source][target],
                        "source_module": source,
                        "target_module": target,
                        "reasons": reasons
                    }
                    for (source, target), reasons
                    in obj.reimports.items()
                ],
                "cycles": [
                    [
                        {
                            "location": location,
                            "target": node
                        }
                        for node, location
                        in zip(cycle_nodes, cycle_locations)
                    ]
                    for cycle_nodes, cycle_locations
                    in obj.circular_dependencies.items()
                ]
            }
        raise Exception("Object is not serializable by DatabaseJSONEncoder")

class ImportGraph:
    """
    An import graphs contains all files imported by a root file with respect to a given environment.
    If a file was not present in the environment during construction the import of it stay hidden.
    Also allows for import optimization as well as circular dependency checks.
    """
    def __init__(self, root, imports, throw_on_circular_dependency, optimize=True):
        """ Initializes an import graph
        
        Fills the 'reimports' member with mapping of:
            tuple(error location, imported file) -> list(reason location)

        If circular dependencies are tolerated, then self.circular_dependencies is a map of
            (location of import that causes a cycle)->(list of files that are part of that cycle)
        with cycle[0] being the file imported again, and cycle[-1] the file causing the error

        If cycles are not tolerated, then the cycle will still be recorded in self.circular_dependencies
        before the error is thrown.

        Arguments:
            :param root: Path to the graph root
            :param imports: Map of source module -> target module -> location
            :param throw_on_circular_dependency: Throws errors instead of recording cycles in self.circular_dependencies
            :param analyze: Toggles import optimization.
        """

        # map of (modules in a cycle) -> [list of import locations of the nodes in the cycle]
        self.circular_dependencies = dict()
        # map of (location of import that causes a cycle)->(list of all cycles caused by that import location)
        self.reimports = dict()
        # map of source->map(target->location)
        self.graph = dict()
        # map of location->target for failed imports
        self.failed_to_import = dict()

        self.root = root
        queue = set([(root, None)])
        while queue:
            module, location = queue.pop()
            if module in self.graph:
                continue
            self.graph.setdefault(module, dict())
            if module not in imports:
                self.failed_to_import[location] = module
                continue
            for target, import_location in imports[module].items():
                self.graph[module][target] = import_location
                queue.add((target, import_location))

        def optimize_imports(node, location, visiting, import_location_stack, cache):
            """ Finds unoptimized imports and cycles
            Arguments:
                :param node: The currently visited node
                :param location: Location of import (for circular dependency debugging)
                :param visiting: Stack of currently visited nodes to prevent circular dependencies
                :param import_location_stack: Stack of locations of currently visiting imports
                :param cache: A map of already visited node's optimize_imports() call results
            Returns:
                Set of all imported files
            """
            if node in visiting:
                # register new cycle with (nodes in the cycle)->(location of import for each node)
                self.circular_dependencies[tuple(visiting[1:] + [node])] = tuple(import_location_stack[1:] + [location])
                if throw_on_circular_dependency:
                    raise CircularDependencyException(location, node, visiting.copy())
                return set(self.graph[node])
            # if not already cached
            if node not in cache:
                # mark as currently processing by pushing on top of stack
                visiting.append(node)
                import_location_stack.append(location) # also record location of where the node was imported
                # Dict of all imports and a log of their import locations
                all_imports = set()
                # for all direct imports
                for direct, direct_loc in self.graph[node].items():
                    # get the files imported by this direct import
                    for indirect in optimize_imports(direct, direct_loc, visiting, import_location_stack, cache):
                        # record this node's full import list
                        all_imports.add(indirect)
                        if indirect in self.graph[node]:
                            # if the import of node->indirect exists
                            # then the import of node->direct at the location 'direct_loc' is not needed because direct->indirect exists.
                            # Add the mapping of (source module, unneeded imported module)->list(reason)
                            self.reimports.setdefault((node, indirect), list()).append(direct_loc)
                for direct in self.graph[node]:
                    all_imports.add(direct)
                # cache the all_imports
                cache[node] = all_imports
                # remove self from stack
                import_location_stack.pop()
                visiting.pop()
            # return cached value
            return cache[node]
        if optimize:
            self.modules = optimize_imports(root, None, list(), list(), dict())
            self.modules.add(root)
    
    def __iter__(self):
        return iter(self.graph)

    @property
    def image(self):
        """ Renders the graph and returns a numpy image. """
        with tempfile.NamedTemporaryFile('w+b') as ref:
            path = self.write_image(ref.name)
        return np.array(Image.open(path))
    
    def write_image(self, path, reimport_color='red', cycle_color='green', edge_color='black', failed_import_color='red'):
        """ Writes the graph to disk.
        Arguments:
            :param path: Path to a save location. If it is a directory, then a randomly named file will be created there, if enabled.
            :param reimport_color: Color of edeges for reimports.
            :param cycle_color: Color of edeges for cycles.
            :param edge_color: Color of other edeges.
            :param failed_import_color: Color of nodes that weren't imported correctly.
        """
        dot = pydot.Dot(graph_type='digraph')
        for source in self.graph:
            if source in self.failed_to_import.values():
                dot.add_node(pydot.Node(source, style='dashed', fontcolor=failed_import_color))
            else:
                dot.add_node(pydot.Node(source))
            for target, loc in self.graph[source].items():
                is_reimport = (source, target) in self.reimports
                is_cycle = cycle_color is not None and any(target in cycle and source in cycle for cycle in self.circular_dependencies)
                if is_cycle:
                    color = cycle_color
                elif is_reimport:
                    color = reimport_color
                else:
                    color = edge_color
                edge = pydot.Edge(source, target, color=color)
                dot.add_edge(edge)
        dot.write_png(path)
        return path
    
    def open_in_image_viewer(self, previous_render_path=None, image_viewer=None):
        """ Renders the graph to a tempfile, then opens it in the default image viewer of the computer.
        
        Arguments:
            :param previous_render_path: If set, draws the image at the given path instead of rendering a new graph to a new tempfile.
            :param image_viewer: Optional image viewer. Default image viewer is used if 'None'.
        """
        image_viewer = image_viewer or {'linux':'xdg-open', 'win32':'explorer', 'darwin':'open'}[sys.platform]
        if previous_render_path:
            subprocess.run([image_viewer, previous_render_path])
            return previous_render_path
        else:
            with tempfile.NamedTemporaryFile(delete=False) as file:
                self.write_image(file.name)
                file.flush()
                subprocess.run([image_viewer, file.name])
                return file.name

class Database(FileWatcher):
    def __init__(self):
        super().__init__(['.tex'])
        self._directories = set()
        self._documents = dict()

        # created on adding a file
        self._module_documents = dict()
        self._map_module_to_file = dict()
        self._map_file_to_module = dict()
        self._binding_documents = dict()

        # created on linking modules with imported modules and their bindings
        self._map_module_to_bindings = dict()
        self._map_module_to_imported_modules = dict()
        self._map_binding_file_to_module = dict()

    def update(self, n_jobs=None, debug=False):
        # add new files from added directories
        self._update_directories()
        # get updated and deleted files from watch list
        deleted, modified = super().update()
        # skip if nothing changed
        if not (deleted or modified):
            return deleted, modified

        # debug output
        if debug:
            if modified:
                print("Modified:")
                for f in modified:
                    print('\t', f)
            if deleted:
                print("Deleted:")
                for f in deleted:
                    print('\t', f)

        # clear all files that were changed
        for file in itertools.chain(deleted, modified):
            self._clear_file(file)

        # Parse all files in parallel or sequential
        with multiprocessing.Pool(n_jobs) as pool:
            documents = pool.map(DatabaseDocument, modified)
        
        # filter failed files
        documents = list(filter(lambda doc: doc.success, documents))

        # add all successfully parsed files
        for doc in documents:
            self._documents[doc.file] = doc

            # Compute file module and binding mappings
            if doc.module:
                self._add_module(doc)
            elif doc.binding:
                self._add_binding(doc)

        # Compute mappings that need the full list of modules and bindings        
        self._link(documents, debug)

        # Return true if there changes were made
        return deleted, modified

    def import_graph(self, file, throw_on_circular_dependency=False, optimize=True):
        """ Returns the import graph of the given file or None. Import optimization calculations can be turned of with optimize. """
        module = self.module_of(file)
        if not module:
            # Can't optimize if there is no module this file belongs to
            return None
        return ImportGraph(module, self._map_module_to_imported_modules, throw_on_circular_dependency=throw_on_circular_dependency, optimize=optimize)
    
    def add_directory(self, dir):
        """ Extension for the file watcher. Makes it possible to add directories directly, which will be scanned for new files on update(). """
        if isdir(dir):
            self._directories.add(abspath(dir))
    
    def module_of(self, id):
        """ Returns the module of some id that is either already a module or module file or binding file. """
        if isfile(id):
            file = abspath(id)
            if file in self._module_documents:
                return self._module_documents[file].module.identifier
            return self._map_binding_file_to_module.get(file, None)
        else:
            if id in self._map_module_to_file:
                return id
        return None

    @property
    def defis(self):
        """ All defis in all files. """
        for doc in self._binding_documents.values():
            for defi in doc.binding.defis:
                yield defi

    def defis_reachable(self, file):
        """ Yields all defis that are directly or indirectly imported by the file. """
        graph = self.import_graph(file, False, False)
        if not graph:
            return ()
        for module in graph:
            for binding in self._map_module_to_bindings.get(module, ()):
                for defi in self._binding_documents[binding].binding.defis:
                    yield defi

    @property
    def trefis(self):
        """ All trefis in all documents. """
        for doc in self._binding_documents.values():
            for trefi in doc.binding.trefis:
                yield trefi

    def trefis_reachable(self, file):
        """ Yields all trefis that directly or indirectly imported by the file. """
        graph = self.import_graph(file, False, False)
        if not graph:
            return ()
        for module in graph:
            for binding in self._map_module_to_bindings.get(module, ()):
                for trefi in self._binding_documents[binding].binding.trefis:
                    yield trefi
    
    def modules_reachable(self, file):
        """ Yields all module identifiers reachable by in the import graph. """
        graph = self.import_graph(file, False, False)
        if not graph:
            return ()
        for module in graph:
            yield module
    
    def autocomplete(self, file, context):
        """ Finds labels that complete the given context inside the file.
            Returns:
                Generator of tuples of (label, kind)
                Where kind is either 'module', 'defi', 'folder'.
        """

        # if at a name= location, yield all defis names that already have a name
        name_context = re.compile(r"""defi+s?\[name=([\w\-]*)$""")
        m = name_context.search(context)
        if m:
            for defi in self.defis_reachable(file):
                name = defi.name
                if name and (not m.group(1) or name.startswith(m.group(1))):
                    yield (name.translate(str.maketrans({'"':'\\"','\n':'','\r':''})), 'defi')
            return

        # check if at a trefi[module..] location,
        module_context = re.compile(r"""trefi+s?\[(\w*)$""")
        m = module_context.search(context)
        if m:
            # yield all module names
            for module in self.modules_reachable(file):
                module_name = module.split('/')[-1]
                if not m.group(1) or module_name.startswith(m.group(1)):
                    yield (module_name, 'module')
            return

        # check if at a trefi[module?defi location
        symbol_context = re.compile(r"""trefi+s?\[(.*)\?(\w*)$""")
        m = symbol_context.search(context)
        if m:
            # yield all defi names or tokens concatenated with '-'
            module = self._resolve_module_at_file(file, m.group(1))
            if module:
                for binding in self._map_module_to_bindings.get(module, ()):
                    if binding not in self._binding_documents:
                        # ignore errors
                        continue
                    for defi in self._binding_documents[binding].binding.defis:
                        name = defi.name
                        if not name: # TODO: Don't know if this is what you want
                            name = '-'.join(defi.tokens).lower()
                        if not m.group(2) or name.startswith(m.group(2)):
                            yield (name.translate(str.maketrans({'"':'\\"','\n':'','\r':''})), 'defi')
            return

        # check if at a trefi{...} location
        symbol_context = re.compile(r"""tref(i+)s?(?:\[([^?]*)(?:\?(.*))?\])?((?:\{.*\})*(?:\{[^\}]*)?)$""")
        m = symbol_context.search(context)
        if m:
            num_is = len(m.group(1))
            module = m.group(2)
            module_symbol = m.group(3)
            filter_text = m.group(4)
            # yield all defi names or tokens concatenated with '-'
            module = self._resolve_module_at_file(file, module) if module else self.module_of(file)
            if module:
                for binding in self._map_module_to_bindings.get(module, ()):
                    if binding not in self._binding_documents:
                        # ignore errors
                        continue
                    for defi in self._binding_documents[binding].binding.defis:
                        if len(defi.tokens) != num_is:
                            continue
                        
                        if module_symbol:
                            name = defi.name
                            if not name: # TODO: Don't know if this is what you want
                                name = '-'.join(defi.tokens).lower()
                            if module_symbol != name:
                                continue
                        label = '}{'.join(defi.tokens)
                        if not filter_text or ('{' + label).startswith(filter_text):
                            yield (label.translate(str.maketrans({'"':'\\"','\n':'','\r':''})), 'text')
            return
        
        # check if referencing a module in a mhmodnl line
        binding_module_name = re.compile(r"""mhmodnl.*{(.*)$""")
        m = binding_module_name.search(context)
        if m:
            own_dir = abspath(dirname(file))
            # yield modules in the same directory
            for module_doc in self._module_documents.values():
                if dirname(module_doc.file) == own_dir and module_doc.module.module.startswith(m.group(1)):
                    yield (module_doc.module.module, 'module')
            return

        # check if in gimport directory statement
        gimport_dir_context = re.compile(r"""gimport\[([\w\/]*)$""")
        m = gimport_dir_context.search(context)
        if m:
            # yield all modules 
            for module in self._module_documents.values():
                if module.module.repository.startswith(m.group(1)):
                    yield (module.module.repository, 'folder')
            return

        # check if in gimport module statement
        gimport_module_context = re.compile(r"""gimport\[([\w\/]+)\]\{(\w*)$""")
        m = gimport_module_context.search(context)
        if m:
            # yield all modules that match the current string
            for module in self._module_documents.values():
                if module.module.identifier.startswith(join(m.group(1), m.group(2))):
                    yield (module.module.module, 'module')
            return

        # check if in LOCAL gimport module statement
        gimport_local_module_context = re.compile(r"""gimport\{(\w*)$""")
        m = gimport_local_module_context.search(context)
        if m:
            module = self.module_of(file)
            modfile = self._map_module_to_file.get(module)
            if modfile and modfile in self._module_documents:
                # get the repo of the current file
                repo = self._module_documents[modfile].module.repository
                for module2 in self._module_documents.values():
                    # then get all module names in the current repo
                    if module2.module.repository == repo:
                        if module2.module.module.startswith(m.group(1)):
                            yield (module2.module.module, 'module')
    
    def find_references(self, file, line, column):
        """ Yields locations that reference this defi or module. """
        self._check_file_tracked(file)
        self._check_file_parsed(file)


        # case 1: Position is a module -> yield all references to that module
        module = self._module_under_position(file, line, column)
        if module:
            # yield all modules that import this file
            for module_doc in self._module_documents.values():
                if module in self._map_module_to_imported_modules.get(module_doc.module.identifier, ()):
                    for target, gimport in module_doc.module.imports.items():
                        if target == module:
                            yield gimport
            # yield all bindings
            for binding_path in self._map_module_to_bindings.get(module, ()):
                if binding_path in self._binding_documents:
                    yield self._binding_documents[binding_path].binding
            # yield all trefis that use this module
            for trefi in self.trefis_reachable(file):
                if self._resolve_trefi_target_module(trefi) == module:
                    yield trefi.symbol                

        # case 2: Position is a defi -> show all references to that defi
        defi = self._defi_under_position(file, line, column)
        if not defi:
            # case 3: A trefi, that points to a defi -> show all references to that defi
            trefi = self._trefi_under_position(file, line, column)
            if trefi:
                for defi in self._resolve_trefi(trefi):
                    # simply assign the defi, then break
                    break
        if defi:
            # yield all trefis that are reachable from this file and that reference the defi
            for trefi in self.trefis_reachable(file):
                if self._check_trefi_defi_id_equal(trefi, defi):
                    yield trefi.symbol
    
    def goto_definition(self, file, line, column):
        """ Returns location of the definition of the symbol under the position and the range of the symbol being defined.
        Returns:
            tuple of "range of defined symbol" and "range of definition location"
        """
        self._check_file_tracked(file)
        self._check_file_parsed(file)

        module = self._module_under_position(file, line, column, return_range=True)
        if module:
            range, module = module
            if module:
                yield range, self._module_documents.get(self._map_module_to_file.get(module)).module

        trefi = self._trefi_under_position(file, line, column)
        if trefi:
            for defi in self._resolve_trefi(trefi):
                yield trefi.range, defi.symbol
        
        defi = self._defi_under_position(file, line, column, return_range=True)
        if defi:
            range, defi = defi
            yield range, defi.symbol
    
    def find_missing_imports(self, file:str):
        """ Yields a list of tuple(error location, modules that might need to be imported in order to find a defi for the trefi at error location). """
        self._check_file_tracked(file)
        self._check_file_parsed(file)

        graph = self.import_graph(file, False, False)
        if not graph:
            return
        file = abspath(file)
        if file not in self._binding_documents:
            # only do this operation for binding documents
            return
        # for all trefis in the specified file
        for trefi in self._binding_documents[file].binding.trefis:
            # check if the trefi already has a partner
            target = list(self._resolve_trefi(trefi))
            # only try to find imports for trefis that can't resolve a defi
            if not target:
                # go through all defis
                for defi in self.defis:
                    if self._check_trefi_defi_id_equal(trefi, defi):
                        yield trefi.symbol, self.module_of(defi.symbol.file)
    
    def find_unresolved_symbols(self, file:str):
        """ Returns tuples of locations of unresolved symbols in a file and the symbol identifier that is unresolved. """
        self._check_file_tracked(file)
        self._check_file_parsed(file)

        graph = self.import_graph(file, False, True)
        if graph:
            for location, gimport in graph.failed_to_import.items():
                yield location, gimport
        doc = self._documents.get(abspath(file))
        if doc and doc.binding:
            for trefi in doc.binding.trefis:
                if not self._resolve_trefi_target_module(trefi):
                    # check if target module can't be resolved
                    yield trefi.symbol, trefi.target_module
                elif not list(self._resolve_trefi(trefi)):
                    # else check if the symbol itself can't be resolved
                    yield trefi.symbol, '-'.join(trefi.tokens)

    @property
    def errors(self):
        """ Accumulates all errors in all files. """
        return [error for doc in self._documents.values() for error in doc.errors]
    
    def find_possible_defis(self, *trefis):
        """ Returns possible defis, that a list of tokens may be referencing
        Arguments:
            :param trefis: A list of tuples. Each tuple of tokens representing a possible trefi.
        
        Returns:
            For each trefi given, returns a list of possible matching defis.
        """
        for tokens in trefis:
            assert isinstance(tokens, tuple)
            yield [
                defi
                for defi in self.defis
                if defi.tokens == tokens
                or defi.name == '-'.join(tokens)
            ]
    
    def _check_file_tracked(self, file:str):
        if file not in self._files:
            raise Exception("File not tracked")
    
    def _check_file_parsed(self, file:str):
        if file not in self._map_file_to_module and file not in self._map_binding_file_to_module:
            raise Exception("File without module or not parsed")
    
    def _resolve_trefi(self, trefi:SubSymbol):
        """ Resolves the trefi to reachable defis. """
        for defi in self.defis_reachable(trefi.symbol.file):
            if self._check_trefi_defi_id_equal(trefi, defi):
                yield defi
    
    def _check_trefi_defi_id_equal(self, trefi:SubSymbol, defi:SubSymbol):
        """ Returns true if the tokens/names match. """

        # module check
        target_module = trefi.target_module
        defi_module = self.module_of(defi.symbol.file)
        
        # if the defi doesn't have a module they can't match
        if not defi_module:
            return False
        
        if target_module:
            if defi_module != target_module and not defi_module.endswith('/' + target_module):
                # Can't match if target module has no way of matching the defi module
                return False
        elif defi_module != self.module_of(trefi.symbol.file):
            # can't match if modules don't match
            return False

        # tokens/name check
        target_symbol = trefi.target_symbol
        if target_symbol:
            # check trefi symbol
            if target_symbol != defi.name and (target_symbol,) != defi.tokens:
                return False
        else:
            # check trefi tokens
            if not (trefi.tokens in ((defi.name,), defi.tokens) or
                '-'.join(trefi.tokens) in (defi.name, '-'.join(defi.tokens))):
                return False

        return True

    def _module_under_position(self, file, line, column, return_range=False):
        """ Returns the module under the position.
            Case 1 \\begin{mhmodnl}{module}{lang}:
                If at 'module'.
                Returns the module the binding file belongs to.

            Case 2 \\trefi[module?...]{...}:
                If at 'module'.
                Resolves 'module' from the file the trefi is located at.
            
            Case 3 \\begin{modsig}{module} ...:
                While above 'module'
                Returns the file itself.

            Case 4 \\gimport[repository]{module}:
                Anywhere at a gimport.
                Returns the module the gimport points to.

        Arguments:
            :param return_range: If true, returns a pair of (region in file -> module) instead.
        """
        # if it is a binding document
        doc = self._documents.get(abspath(file))
        position = Position(line, column)
        if doc and doc.binding:
            # check if the cursor is at the mmodnl signature
            if doc.binding.range.contains(position):
                if return_range:
                    return doc.binding.range, self._map_binding_file_to_module[doc.file] # case 1
                else:
                    return self._map_binding_file_to_module[doc.file] # case 1
            # else get check if there is a trefi at the position
            for trefi in doc.binding.trefis:
                if trefi.target_module and trefi.target_module_range.contains(position):
                    target_module = self._resolve_trefi_target_module(trefi)
                    if return_range and target_module:
                        return trefi.target_module_range, target_module # case 2
                    else:
                        return target_module # case 2
        elif doc and doc.module:
            # else module
            if doc.module.range.contains(position):
                if return_range:
                    return doc.module.range, doc.module.identifier # Case 3
                else:
                    return doc.module.identifier # Case 3
            gimport = self._import_under_position(file, line, column)
            if gimport:
                # return the module under the position
                target, gimport = gimport
                if return_range and target:
                    return gimport.range, target # case 4
                else:
                    return target # case 4
        return None
    
    def _trefi_under_position(self, file, line, column):
        """ Returns the trefi under the specified position in a file. """
        doc = self._binding_documents.get(abspath(file))
        if not doc:
            return None
        position = Position(line, column)
        for trefi in doc.binding.trefis:
            assert isinstance(trefi, SubSymbol)
            if trefi.contains(position):
                return trefi
    
    def _defi_under_position(self, file, line, column, return_range=False):
        """ Returns the defi under the specified position in a file. """
        doc = self._binding_documents.get(abspath(file))
        if not doc:
            return None
        position = Position(line, column)
        # case 1: \adefi[...]{symbol1}{symbol2a}{symbol2b}
        # symbol1 and symbol2x are discoverable symbols
        for defi in doc.binding.defis:
            assert isinstance(defi, SubSymbol)
            if defi.contains(position):
                if return_range:
                    return defi.range, defi
                else:
                    return defi
        # case 2: \trefi[module?defi]{...}
        # Here defi should be discoverable
        for trefi in doc.binding.trefis:
            assert isinstance(trefi, SubSymbol)
            if trefi.target_symbol and trefi.target_symbol_range.contains(position):
                for defi in self._resolve_trefi(trefi):
                    # return the first match only..
                    if return_range:
                        return trefi.target_symbol_range, defi
                    else:
                        return defi
        return None
    
    def _import_under_position(self, file, line, column):
        """ Returns the import under the specified position. """
        doc = self._module_documents.get(abspath(file))
        if not doc:
            return None
        position = Position(line, column)
        for target, gimport in doc.module.imports.items():
            if gimport.range.contains(position):
                return target, gimport
    
    def _resolve_trefi_target_module(self, symbol:SubSymbol):
        """ Resolves the module pointed to by the symbol. Returns None if not found. """
        module = symbol.target_module
        if not module:
            # no target symbol is specified, return the module of the current file
            return self._map_binding_file_to_module.get(symbol.symbol.file)
        # Else resolve the module the symbol is pointing to from the file the symbol is from
        return self._resolve_module_at_file(symbol.symbol.file, module)
    
    def _resolve_module_at_file(self, file:str, module:str):
        """ Returns the full module identifier if it is reachable from the file. """
        for graph_module in self.import_graph(file, False, False) or ():
            if graph_module == module or graph_module.endswith('/' + module):
                return graph_module
        return None
    
    def _add_module(self, doc):
        """ Adds a module to the database. """
        assert doc.module
        if doc.file in self._module_documents:
            raise RuntimeError("Duplicate add of module %s previously was: %s" % (doc.file, self._module_documents[doc.file].file))
        self._module_documents[doc.file] = doc
        self._map_module_to_file[doc.module.identifier] = doc.file
        self._map_file_to_module[doc.file] = doc.module.identifier
        self._map_module_to_bindings[doc.module.identifier] = set()
        self._map_module_to_imported_modules[doc.module.identifier] = {
            target: location
            for target, location in doc.module.imports.items()
        }
    
    def _remove_module(self, doc):
        """ Reverses add_module(). """
        assert doc.module
        del self._module_documents[doc.file]
        del self._map_module_to_file[doc.module.identifier]
        del self._map_file_to_module[doc.file]
        del self._map_module_to_imported_modules[doc.module.identifier]
        # remove all binding links
        for binding in self._map_module_to_bindings[doc.module.identifier]:
            if binding in self._map_binding_file_to_module:
                # set linked bindings to None
                self._map_binding_file_to_module[binding] = None
        del self._map_module_to_bindings[doc.module.identifier]

    def _add_binding(self, doc):
        """ Adds a binding to the database. """
        assert doc.binding
        self._binding_documents[doc.file] = doc
        self._map_binding_file_to_module[doc.file] = None

    def _remove_binding(self, doc):
        """ Reverses add_binding(). """
        assert doc.binding
        del self._binding_documents[doc.file]

        # remove all binding links
        if self._map_binding_file_to_module[doc.file]:
            module_bindings = self._map_module_to_bindings[self._map_binding_file_to_module[doc.file]]
            assert isinstance(module_bindings, set)
            if doc.file in module_bindings:
                module_bindings.remove(doc.file)
        del self._map_binding_file_to_module[doc.file]
    
    def _clear_file(self, file):
        """ Removes a file from the database. """
        file = abspath(file)
        if file not in self._documents:
            return False
        doc =  self._documents[file]
        if doc.module:
            self._remove_module(doc)
        elif doc.binding:
            self._remove_binding(doc)
        del self._documents[file]
        return True
    
    def _link(self, documents, debug=False):
        """ Creates mappings that need all files in the database parsed. """

        # first update modules
        for doc in documents:
            if debug: print("LINK\t", relpath(doc.file))
            if doc.module:
                # create module binding mappings for this file                    
                self._map_module_to_bindings[doc.module.identifier] = set(
                    binding_doc.file
                    for binding_doc in self._binding_documents.values()
                    if dirname(doc.file) == dirname(binding_doc.file)
                    and doc.module.name == binding_doc.binding.bound_module)

                # then we know, that all the files this module links to have to link back to this module
                for binding_path in self._map_module_to_bindings[doc.module.identifier]:
                    if debug: print("LINK MODULE\t", relpath(binding_path), doc.module.identifier)
                    self._map_binding_file_to_module[binding_path] = doc.module.identifier

            elif doc.binding:
                success = False
                # find the module, that this binding belongs to
                for module_doc in self._module_documents.values():
                    if (module_doc.module.name == doc.binding.bound_module and
                        dirname(module_doc.file) == dirname(doc.file)):
                        if debug: print("LINK BINDING\t", relpath(doc.file), module_doc.module.identifier)

                        # Link the matching module
                        self._map_binding_file_to_module[doc.file] = module_doc.module.identifier

                        # Also add this to the inverse map
                        self._map_module_to_bindings[module_doc.module.identifier].add(doc.file)

                        # signal success and stop searching for a module
                        success = True 
                        break
                if not success:
                    # no matchin module found
                    if debug: print("LINK BINDING FAILED\t", doc.binding)
    
    def _update_directories(self):
        """ Adds all files of watched directories. """
        for d in list(self._directories):
            if not isdir(d):
                self._directories.remove(d)
            else:
                self.add(f'{d}/*')

# db = Database()
# for dir in glob('data/smglom/**/source'):
#     db.add_directory(dir)
# db.update()