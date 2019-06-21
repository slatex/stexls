from __future__ import annotations
from typing import List, Dict, Optional
from glob import glob
import os
import itertools
import multiprocessing

from trefier.misc.location import *
from trefier.misc.file_watcher import FileWatcher
from trefier.misc.rwlock import RWLock, async_writer, async_reader
from trefier.models import seq2seq

from trefier.linting.exceptions import *
from trefier.linting.document import *
from trefier.linting.imports import ImportGraph

__all__ = ['Linter']


class Linter(FileWatcher):
    def load_tagger_model(self, path: str):
        if seq2seq.Seq2SeqModel.verify_loadable(path):
            self.tagger = seq2seq.Seq2SeqModel.load(path)
            self.tagger_path = os.path.abspath(path)
            for module, bindings in self._map_module_identifier_to_bindings.items():
                for lang, binding in bindings.items():
                    if lang == 'en' and binding.file not in self.tags:
                        self.tags[binding.file] = self.tagger.predict(binding.file)
        else:
            raise LinterInternalException.create(path, 'Unable to load tagger model')

    @async_writer(lambda self: self._rwlock)
    def write(self, delay):
        from time import sleep
        sleep(delay)
        return 'write done after %f' % delay

    @async_reader(lambda self: self._rwlock)
    def read(self, delay):
        from time import sleep
        sleep(delay)
        return 'read done after %f' % delay

    @async_reader(lambda self: self._rwlock)
    def ls(self):
        return list(self._map_file_to_document)

    @async_reader(lambda self: self._rwlock)
    def modules(self):
        return [
            str(document.module)
            for module, document
            in self._map_module_identifier_to_module.items()
        ]

    @async_reader(lambda self: self._rwlock)
    def bindings(self):
        return [
            str(document.binding)
            for module, bindings
            in self._map_module_identifier_to_bindings.items()
            for lang, document in bindings.items()
        ]

    @async_reader(lambda self: self._rwlock)
    def defis(self):
        return [
            str(defi)
            for module, bindings
            in self._map_module_identifier_to_bindings.items()
            for lang, document in bindings.items()
            for defi in document.defis
        ]

    @async_reader(lambda self: self._rwlock)
    def trefis(self):
        with self._rwlock.reader():
            return [
                str(trefi)
                for module, bindings
                in self._map_module_identifier_to_bindings.items()
                for lang, document in bindings.items()
                for trefi in document.trefis
            ]

    @async_reader(lambda self: self._rwlock)
    def symbols(self):
        return [
            str(symi)
            for module, document
            in self._map_module_identifier_to_module.items()
            for symi in document.symis
        ]

    @async_reader(lambda self: self._rwlock)
    def module_at_position(self, file: str, line: int, column: int):
        doc = self._map_file_to_document.get(file)
        if doc is None:
            raise Exception("File not tracked")

        position = Position(line, column)

        if doc.module is not None:
            if doc.module.range.contains(position):
                return doc.module.module_name

        if doc.binding is not None:
            if doc.binding.range.contains(position):
                return doc.binding.bound_module_name

        for trefi in doc.trefis:
            if trefi.target_module_location is not None:
                if trefi.target_module_location.range.contains(position):
                    return str(trefi.target_module)

        for gimport in doc.gimports:
            if gimport.imported_module_location.range.contains(position):
                return str(gimport.imported_module)
        return None

    @async_writer(lambda self: self._rwlock)
    def add_directory(self, directory):
        added = 0
        for d in glob(directory, recursive=True):
            if os.path.isdir(d):
                if d not in self._watched_directories:
                    self._watched_directories.append(d)
                    added += 1
        return added

    @async_writer(lambda self: self._rwlock)
    def update(self, n_jobs=None, debug=False, use_multiprocessing=True):
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
            return 0

        for file in itertools.chain(deleted, modified):
            try:
                if self._is_linked(file):
                    self._unlink(file)
            except Exception as e:
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
                self.exceptions.setdefault(document.file, [])
                self.exceptions[document.file].append(e)

        self.import_graph.update()

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
            if self.tagger and document.binding.lang == 'en':
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
        super().__init__(['.tex'])
        self._map_file_to_document: Dict[str, Document] = {}
        self._map_module_identifier_to_bindings: Dict[str, Dict[str, Document]] = {}
        self._map_module_identifier_to_module: Dict[str, Document] = {}
        self._watched_directories: List[str] = []
        self._rwlock = RWLock()

        self.failed_to_parse: Dict[str, List[Exception]] = {}
        self.exceptions: Dict[str, List[Exception]] = {}
        self.import_graph = ImportGraph()

        self.tagger_path: Optional[str] = None
        self.tagger: Optional[seq2seq.Model] = None
        self.tags: Dict[str, object] = dict()

    def __getstate__(self):
        return (
            super().__getstate__(),
            self._map_file_to_document,
            self._map_module_identifier_to_bindings,
            self._map_module_identifier_to_module,
            self._watched_directories,
            self.failed_to_parse,
            self.exceptions,
            self.import_graph,
            self.tags,
        )

    def __setstate__(self, state):
        # initialize other state
        self._rwlock = RWLock()
        self.tagger_path = None
        self.tagger = None

        # load state
        (superstate,
         self._map_file_to_document,
         self._map_module_identifier_to_bindings,
         self._map_module_identifier_to_module,
         self._watched_directories,
         self.failed_to_parse,
         self.exceptions,
         self.import_graph,
         self.tags) = state
        super().__setstate__(superstate)
