from __future__ import annotations
from typing import List, Dict, Optional, Iterator, Set
from glob import glob
import os
import itertools
import multiprocessing
import difflib

from trefier.misc.location import *
from trefier.misc.file_watcher import FileWatcher
from trefier.models import seq2seq

from trefier.linting.exceptions import *
from trefier.linting.identifiers import *
from trefier.linting.symbols import *
from trefier.linting.document import *
from trefier.linting.imports import ImportGraph

__all__ = ['Linter']


class Linter:
    def load_tagger_model(self, path: str):
        if self.tagger_path != path:
            # reset tags if a new tagger is loaded
            self.tags.clear()
        if seq2seq.Seq2SeqModel.verify_loadable(path):
            self.tagger = seq2seq.Seq2SeqModel.load(path)
            self.tagger_path = os.path.abspath(path)
            for module, bindings in self._map_module_identifier_to_bindings.items():
                for lang, binding in bindings.items():
                    if lang in ('en', 'lang') and binding.file not in self.tags:
                        self.tags[binding.file] = self.tagger.predict(binding.file)
        else:
            raise LinterInternalException.create(path, 'Unable to load tagger model')

    def ls(self) -> List[str]:
        return list(self._map_file_to_document)

    def modules(self) -> List[ModuleDefinitonSymbol]:
        return [
            document.module
            for module, document
            in self._map_module_identifier_to_module.items()
        ]

    def bindings(self) -> List[ModuleBindingDefinitionSymbol]:
        return [
            document.binding
            for module, bindings
            in self._map_module_identifier_to_bindings.items()
            for lang, document in bindings.items()
        ]

    def defis(self) -> List[DefiSymbol]:
        return [
            defi
            for module, bindings
            in self._map_module_identifier_to_bindings.items()
            for lang, document in bindings.items()
            for defi in document.defis
        ]

    def trefis(self) -> List[TrefiSymbol]:
        return [
            trefi
            for module, bindings
            in self._map_module_identifier_to_bindings.items()
            for lang, document in bindings.items()
            for trefi in document.trefis
        ]

    def symbols(self) -> List[SymiSymbol]:
        return [
            symi
            for module, document
            in self._map_module_identifier_to_module.items()
            for symi in document.symis
        ]

    def goto_definition(self, file: str, line: int, column: int) -> Optional[Symbol]:
        doc = self._map_file_to_document.get(file)
        if doc is None:
            raise Exception("File not tracked")
        module = self._module_at_position(file, line, column)
        if module:
            return self._resolve_module(doc.module_identifier, module)

        symbol = self._named_symbol_at_position(file, line, column)
        if symbol:
            symbol_module, symbol_name = symbol
            return self._resolve_symbol(doc.module_identifier, symbol_name, symbol_module)

    def goto_implementation(self, file: str, line: int, column: int) -> List[Symbol]:
        definition = self.goto_definition(file, line, column)
        implementations = []
        if definition is not None:
            for lang, binding in self._map_module_identifier_to_bindings.get(str(definition.module), {}).items():
                if isinstance(definition, SymiSymbol):
                    for defi in binding.defis:
                        if defi.symbol_name == definition.symbol_name:
                            implementations.append(defi)
                elif isinstance(definition, ModuleDefinitonSymbol):
                    implementations.append(binding.binding)
        return implementations

    def find_references(self, file: str, line: int, column: int) -> List[Location]:
        definition = self.goto_definition(file, line, column)
        references = []
        if definition is not None:
            file_module = str(ModuleIdentifier.from_file(file))
            for lang, binding in self._map_module_identifier_to_bindings[str(definition.module)].items():
                if isinstance(definition, SymiSymbol):
                    for defi in binding.defis:
                        if defi.symbol_name == definition.symbol_name:
                            if defi.name_argument_location:
                                references.append(defi.name_argument_location)
                            else:
                                references.append(defi.symbol_name_locations[-1])
                elif isinstance(definition, ModuleDefinitonSymbol):
                    references.append(binding.binding)
            for module in self.import_graph.reachable_modules_of(file_module):
                for lang, binding in self._map_module_identifier_to_bindings[module].items():
                    for trefi in binding.trefis:
                        if isinstance(definition, SymiSymbol):
                            if (trefi.target_module == definition.module
                                    and trefi.symbol_name == definition.symbol_name):
                                references.append(trefi)
                        elif isinstance(definition, ModuleDefinitonSymbol):
                            if (trefi.target_module_location
                                    and trefi.target_module == definition.module
                                    and trefi.symbol_name == definition.module_name):
                                references.append(trefi.target_module_location)

        return references

    def add(self, directory):
        added = 0
        for d in glob(directory, recursive=True):
            if os.path.isdir(d):
                if d not in self._watched_directories:
                    self._watched_directories.append(d)
                    added += 1
        return added

    def update(self,
               n_jobs: Optional[int] = None,
               use_multiprocessing: bool = True):
        # update watched directories
        for dirname in list(self._watched_directories):
            if not os.path.isdir(dirname):
                # remove if no longer valid directory
                self._watched_directories.remove(dirname)
            else:
                # else add all direct files inside it
                self._file_watcher.add(os.path.join(dirname, '*'))

        # update watched file index
        deleted, modified = self._file_watcher.update()
        if not (modified or deleted):
            return {}

        for file in itertools.chain(deleted, modified):
            if self._is_linked(file):
                self._unlink(file)

        # Parse all files in parallel or sequential
        if use_multiprocessing:
            with multiprocessing.Pool(n_jobs) as pool:
                documents = pool.map(Document, modified)
        else:
            documents = list(map(Document, modified))

        #  update exception dictionary
        for document in filter(lambda doc: doc.exceptions, documents):
            self.exceptions.setdefault(document.file, [])
            self.exceptions[document.file].extend(document.exceptions)

        #
        failed_documents: Set[str] = set()
        for failed_document in filter(lambda doc: not doc.success, documents):
            failed_documents.add(failed_document.file)

        for document in filter(lambda doc: doc.success, documents):
            self._link(document)

        linting_errors = dict.fromkeys(deleted | failed_documents)

        for changed_module in self.import_graph.update():
            module_errors = self._get_module_linting_errors(changed_module)
            #linting_errors.update(module_errors)

        self.linting_errors.update(linting_errors)

        return linting_errors

    def _get_module_linting_errors(
            self, module: Union[ModuleIdentifier, str]) -> Dict[str, List[Tuple[Location, str]]]:
        pass

    def _get_possible_trefi_matches(
            self,
            document: Document) -> List[Tuple[Union[ModuleIdentifier, str], str, List[Location]]]:
        """ Looks at the tags for a document and returns possibly matching symbols with the
            source location of the matching tokens.
            :returns List of tuples of (module of match, symbol name of match, List of source tokens in the file) """
        assert document.file in self.tags
        pred, locations, tokens, envs = self.tags[document.file]
        matches = []
        for is_keyword, group in itertools.groupby(enumerate(pred > 0.5), key=lambda x: x[1]):
            if not is_keyword:
                continue
            indices, values = zip(*group)
            loc = [locations[i] for i in indices]
            name = '-'.join(tokens[i] for i in indices)
            for similarity, symi in self._find_similarly_named_symbols(name):
                matches.append((symi.module, symi.symbol_name, loc))
        return matches

    def _find_similarly_named_symbols(self, name: str, threshold: float = 0.8) -> Iterator[Tuple[float, SymiSymbol]]:
        for module, document in self._map_module_identifier_to_module.items():
            for symi in document.symis:
                ratio = difflib.SequenceMatcher(a=symi.symbol_name, b=name).ratio()
                if ratio > threshold:
                    yield (ratio, symi)

    def _resolve_module(self, module: ModuleIdentifier, target: ModuleIdentifier) -> Optional[ModuleDefinitonSymbol]:
        """ Resolves the location of target module given the current module """
        if str(target) in self.import_graph.reachable_modules_of(str(module)):
            return self._map_file_to_document.get(self.import_graph.modules.get(str(target))).module

    def _resolve_symbol(self,
                        module: ModuleIdentifier,
                        symbol_name: str,
                        symbol_module: Optional[ModuleIdentifier] = None) -> Optional[Symbol]:
        """ Resolves a symbol definition given the current module, the symbol name
            and an optional hint of the module that contains the symbol """
        target_module = symbol_module or module
        if not self._resolve_module(module, target_module):
            return None
        if target_module is not None:
            document = self._map_module_identifier_to_module.get(str(target_module))
            if document is not None:
                for symi in document.symis:
                    if symi.symbol_name == symbol_name:
                        return symi
        return None

    def _module_at_position(self, file: str, line: int, column: int) -> Optional[ModuleIdentifier]:
        doc = self._map_file_to_document.get(file)
        if doc is None:
            raise Exception("File not tracked")

        position = Position(line, column)

        if doc.module is not None:
            if doc.module.range.contains(position):
                return doc.module_identifier

        if doc.binding is not None:
            if doc.binding.range.contains(position):
                return doc.module_identifier

        for trefi in doc.trefis:
            if trefi.target_module_location is not None:
                if trefi.target_module_location.range.contains(position):
                    return trefi.target_module

        for gimport in doc.gimports:
            if gimport.imported_module_location.range.contains(position):
                return gimport.imported_module
        return None

    def _named_symbol_at_position(self, file: str, line: int, column: int) -> Optional[Tuple[ModuleIdentifier, str]]:
        doc = self._map_file_to_document.get(file)
        if doc is None:
            raise Exception("File not tracked")
        position = Position(line, column)

        if doc.module:
            for symi in doc.symis:
                if symi.name_contains(position):
                    return symi.module, symi.symbol_name
        elif doc.binding:
            for trefi in doc.trefis:
                if trefi.name_contains(position):
                    return trefi.target_module, trefi.symbol_name

            for defi in doc.defis:
                if defi.name_contains(position):
                    return defi.module, defi.symbol_name
        return None

    def _is_linked(self, file: str) -> bool:
        return self._map_file_to_document.get(file) is not None

    def _unlink(self, file: str):
        """ Deletes all symbols/links provided by the file if tracked. """
        assert self._is_linked(file), "Unable to unlink unlinked file"

        if file in self.exceptions:
            del self.exceptions[file]

        if file in self.tags:
            del self.tags[file]

        document = self._map_file_to_document.get(file)

        module_id = str(document.module_identifier)

        if document.binding:
            print('-BINDING', document.binding.lang, module_id)
            del self._map_module_identifier_to_bindings[module_id][document.binding.lang]
            if not self._map_module_identifier_to_bindings[module_id]:
                del self._map_module_identifier_to_bindings[module_id]
            if document.file in self.tags:
                del self.tags[document.file]
            if document.file in self.possible_trefis:
                del self.possible_trefis[document.file]

        if document.module:
            print('-MODULE', module_id)
            self.import_graph.remove(document.module_identifier)
            del self._map_module_identifier_to_module[module_id]

        if file in self.linting_errors:
            del self.linting_errors[file]

        print('-FILE', file)
        del self._map_file_to_document[file]

    def _link(self, document: Document):
        """ Starts tracking a document. Indexes links and symbols provided by it. """
        assert not self._is_linked(document.file), "Duplicate link"
        print('+FILE', document.file)
        self._map_file_to_document[document.file] = document
        module = str(document.module_identifier)
        if document.binding:
            print("+BINDING", module, document.binding.lang, os.path.basename(document.file))
            self._map_module_identifier_to_bindings.setdefault(module, {})
            if document.binding.lang in self._map_module_identifier_to_bindings[module]:
                raise LinterDuplicateDefinitionException.create(
                    identifier=f'{document.module_identifier}/{document.binding.lang}',
                    new=document.binding,
                    previous=self._map_module_identifier_to_bindings[module][document.binding.lang].binding)
            self._map_module_identifier_to_bindings[module][document.binding.lang] = document
            if self.tagger and document.binding.lang in ('en', 'lang'):
                self.tags[document.file] = self.tagger.predict(document.file)

        if document.module:
            print("+MODULE", module, os.path.basename(document.file))
            if module in self._map_module_identifier_to_module:
                raise LinterDuplicateDefinitionException.create(
                    identifier=module,
                    new=document.module,
                    previous=self._map_module_identifier_to_module[module].module)
            self._map_module_identifier_to_module[module] = document
            self.import_graph.add(document)

    def __init__(self):
        self._file_watcher = FileWatcher(['.tex'])
        self._map_file_to_document: Dict[str, Document] = dict()
        self._map_module_identifier_to_bindings: Dict[str, Dict[str, Document]] = dict()
        self._map_module_identifier_to_module: Dict[str, Document] = dict()
        self._watched_directories: List[str] = []

        self.exceptions: Dict[str, List[Exception]] = dict()
        self.import_graph = ImportGraph()

        # dict of file to list of linting errors of location and message
        self.linting_errors: Dict[str, List[Tuple[Location, str]]] = dict()

        self.tagger_path: Optional[str] = None
        self.tagger: Optional[seq2seq.Model] = None
        self.tags: Dict[str, object] = dict()

        # dict of file to list of possible trefis (module, name, token locations to wrap)
        self.possible_trefis: Dict[str, List[Tuple[ModuleIdentifier, str, List[Location]]]] = dict()

    def __getstate__(self):
        return (
            self._file_watcher,
            self._map_file_to_document,
            self._map_module_identifier_to_bindings,
            self._map_module_identifier_to_module,
            self._watched_directories,
            self.exceptions,
            self.import_graph,
            self.linting_errors,
            self.tagger_path,
            self.tags,
            self.possible_trefis,
        )

    def __setstate__(self, state):
        # initialize other state
        self.tagger = None

        # load state
        (self._file_watcher,
         self._map_file_to_document,
         self._map_module_identifier_to_bindings,
         self._map_module_identifier_to_module,
         self._watched_directories,
         self.exceptions,
         self.import_graph,
         self.linting_errors,
         self.tagger_path,
         self.tags,
         self.possible_trefis,) = state

