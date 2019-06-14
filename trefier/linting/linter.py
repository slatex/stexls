from __future__ import annotations
from typing import List, Dict
from glob import glob
import os
import itertools
import multiprocessing

from trefier.misc.location import *
from trefier.misc.file_watcher import FileWatcher
from trefier.misc.rwlock import RWLock

from trefier.linting.exceptions import *
from trefier.linting.document import *
from trefier.linting.imports import ImportGraph

__all__ = ['Linter']


class Linter(FileWatcher):
    def __init__(self):
        super().__init__(['.tex'])
        self._map_file_to_document: Dict[str, Document] = {}
        self._map_module_identifier_to_bindings: Dict[str, Dict[str, Document]] = {}
        self._map_module_identifier_to_module: Dict[str, Document] = {}
        self._watched_directories: List[str] = []
        self.failed_to_parse: Dict[str, List[Exception]] = {}
        self.exceptions = {}
        self.tagger_path = None
        self.tagger = None
        self._rwlock = RWLock()
        self.import_graph = ImportGraph()

    def load_tagger_model(self, path: str):
        self.tagger_path = os.path.abspath(path)

    @property
    def modules(self):
        return list(self._map_module_identifier_to_module)

    @property
    def bindings(self):
        return list(f'{module}.{lang}'
                    for module, bindings
                    in self._map_module_identifier_to_bindings.items()
                    for lang in bindings)

    @property
    def ls(self):
        return list(self._map_file_to_document)

    @property
    def symbols(self):
        return list(
            f'{module}/{sym.symbol_name}'
            for module, document
            in self._map_module_identifier_to_module.items()
            for sym in document.symis
        )

    @property
    def defis(self):
        return {
            f'{module}.{lang}': document.defis
            for module, bindings
            in self._map_module_identifier_to_bindings.items()
            for lang, document in bindings.items()
        }

    @property
    def trefis(self):
        return {
            f'{module}.{lang}': document.trefis
            for module, bindings
            in self._map_module_identifier_to_bindings.items()
            for lang, document in bindings.items()
        }

    def module_at_position(self, file, line, column):
        with self._rwlock.reader():
            doc: Document = self._map_file_to_document.get(file)
            if doc is None:
                raise Exception("File not tracked currently")

            position = Position(line, column)

            for trefi in doc.trefis:
                if trefi.target_module_location is not None:
                    if trefi.target_module_location.range.contains(position):
                        yield str(trefi.target_module_location)

            for gimport in doc.gimports:
                if gimport.imported_module_location.range.contains(position):
                    yield str(gimport.imported_module_location)

    def add_directory(self, directory):
        with self._rwlock.writer():
            added = 0
            for d in glob(directory, recursive=True):
                if os.path.isdir(d):
                    if d not in self._watched_directories:
                        self._watched_directories.append(d)
                        added += 1
            return added

    def update(self, n_jobs=None, debug=False, use_multiprocessing=True):
        with self._rwlock.writer():
            # update watched directories
            for d in list(self._watched_directories):
                if not os.path.isdir(d):
                    # remove if no longer valid directory
                    self._watched_directories.remove(d)
                else:
                    # else add all direct files inside it
                    self.add(f'{d}/*')

            # update watched file index
            deleted, modified = super().update()
            if not (modified or deleted):
                return None

            for file in itertools.chain(deleted, modified):
                try:
                    if self._is_linked(file):
                        self._unlink(file)
                except Exception as e:
                    raise
                    self.exceptions.setdefault(file, [])
                    self.exceptions[file].append(e)

            # Parse all files in parallel or sequential
            if use_multiprocessing:
                with multiprocessing.Pool(n_jobs) as pool:
                    documents = pool.map(Document, modified)
            else:
                documents = list(map(Document, modified))

            for failed_document in filter(lambda doc: not doc.success, documents):
                self.failed_to_parse[failed_document.file] = failed_document.exceptions

            for document in filter(lambda doc: doc.success, documents):
                if document.exceptions:
                    self.exceptions.setdefault(document.file, [])
                    self.exceptions[document.file].extend(document.exceptions)
                try:
                    self._link(document)
                except Exception as e:
                    raise
                    self.exceptions.setdefault(document.file, [])
                    self.exceptions[document.file].append(e)

            return len(documents)

    def _is_linked(self, file: str) -> bool:
        return self._map_file_to_document.get(file) is not None

    def _unlink(self, file: str):
        """ Deletes all symbols/links provided by the file if tracked. """
        assert self._is_linked(file), "Unable to unlink unlinked file"

        if file in self.exceptions:
            del self.exceptions[file]

        if file in self.failed_to_parse:
            del self.failed_to_parse[file]

        document = self._map_file_to_document.get(file)

        module_id = str(document.module_identifier)

        if document.binding:
            print('-BINDING', document.binding.lang, module_id)
            del self._map_module_identifier_to_bindings[module_id][document.binding.lang]
            if not self._map_module_identifier_to_bindings[module_id]:
                del self._map_module_identifier_to_bindings[module_id]

        if document.module:
            print('-MODULE', module_id)
            self.import_graph.remove(document.module_identifier)
            del self._map_module_identifier_to_module[module_id]

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

        if document.module:
            print("+MODULE", module, os.path.basename(document.file))
            if module in self._map_module_identifier_to_module:
                raise LinterDuplicateDefinitionException.create(
                    identifier=module,
                    new=document.module,
                    previous=self._map_module_identifier_to_module[module].module)
            self._map_module_identifier_to_module[module] = document
            self.import_graph.add(document)

    def __getstate__(self):
        return (
            super().__getstate__(),
            self.tagger_path,
            self._map_file_to_document,
            self._map_module_identifier_to_bindings,
            self._map_module_identifier_to_module,
            self._watched_directories,
            self.failed_to_parse,
            self.import_graph,
            self.exceptions
        )

    def __setstate__(self, state):
        # initialize other state
        self._rwlock = RWLock()
        self.tagger_path = None
        self.tagger = None

        # load state
        (superstate,
         tagger_path,
         self._map_file_to_document,
         self._map_module_identifier_to_bindings,
         self._map_module_identifier_to_module,
         self._watched_directories,
         self.failed_to_parse,
         self.import_graph,
         self.exceptions) = state
        super().__setstate__(superstate)

        # load extra state
        if tagger_path:
            self.load_tagger_model(tagger_path)
