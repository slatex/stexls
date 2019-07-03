from __future__ import annotations
from typing import List, Dict, Optional, Iterator, Set
from glob import glob
import os
import itertools
import multiprocessing
import difflib
import re
from functools import partial

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
        if seq2seq.Seq2SeqModel.verify_loadable(path):
            self.tagger = seq2seq.Seq2SeqModel.load(path)
            self.tagger_path = os.path.abspath(path)
            self.tags = dict()
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

    def _update_watched_directories(self):
        for dirname in list(self._watched_directories):
            if not os.path.isdir(dirname):
                # remove if no longer valid directory
                self._watched_directories.remove(dirname)
            else:
                # else add all direct files inside it
                self._file_watcher.add(os.path.join(dirname, '*'))
        return self._file_watcher.update()

    def update(self,
               n_jobs: Optional[int] = None,
               use_multiprocessing: bool = True,
               debug: bool = False):
        # get file changes
        deleted, modified = self._update_watched_directories()
        if not (modified or deleted):
            return {}

        # remove all changed files
        for file in itertools.chain(deleted, modified):
            if self._is_linked(file):
                self._unlink(file, silent=not debug)

        # Parse all files in parallel or sequential
        if use_multiprocessing and not debug:
            with multiprocessing.Pool(n_jobs) as pool:
                documents = pool.map(Document, modified)
        else:
            constructor = partial(Document, ignore_exceptions=False) if debug else Document
            documents = list(map(constructor, modified))

        # link successfully compiled documents
        for document in filter(lambda doc: doc.success, documents):
            self._link(document, silent=not debug)

        # get all modules that were changed
        changed_modules = self.import_graph.update()

        report: Dict[str, Optional[List[ReportEntry]]] = dict(self.make_report())

        # add exceptions from not successfully compiled documents to report
        for document in filter(lambda doc: not doc.success, documents):
            report.setdefault(document.file, [])
            report[document.file].extend(ReportEntry.error(document.file, e) for e in document.exceptions)
            if document.syntax_errors:
                for syntax_error_location, information in document.syntax_errors.items():
                    report[document.file].append(
                        ReportEntry.syntax_error(
                            syntax_error_location, message=information['msg'], symbol=information['symbol']))

        # set all other unhandled files to None in order to mark them as deleted
        for unhandled in itertools.chain(deleted, modified):
            report.setdefault(unhandled)
            if not report[unhandled]:
                report[unhandled] = None

        return report

    def make_report(self, documents: Optional[List[Document]] = None) -> Iterator[Tuple[str, List[ReportEntry]]]:
        if not documents:
            documents = list(self._map_file_to_document.values())

        for document in documents:
            yield (document.file, list(self._make_document_report(document)))

    def _documents_in_module(self, module: Union[ModuleIdentifier, str]) -> Iterator[Document]:
        """ Returns an iterator for all files assigned to that module """
        module_document = self._map_module_identifier_to_module.get(str(module))
        if module_document:
            yield module_document
        yield from self._map_module_identifier_to_bindings.get(module, {}).values()

    def _make_document_binding_report(self, document: Document) -> Iterator[ReportEntry]:
        # check wether the module of the filename matches environment
        if document.binding.module_and_file_name_mismatch:
            yield ReportEntry.module_name_mismatch(document.binding)

        # check wether the language of the filename matches the environment
        if document.binding.module_lang_and_file_name_lang_mismatch:
            yield ReportEntry.binding_lang_mismatch(document.binding)

        # report module defined
        if str(document.module_identifier) not in self._map_module_identifier_to_module:
            yield ReportEntry.unresolved(document.binding, str(document.module_identifier))

        # report undefined trefis
        for trefi in document.trefis:
            if not self._resolve_module(trefi.module, trefi.target_module):
                # create unresolved report if trefi module not resolved
                location = trefi.target_module_location or trefi
                yield ReportEntry.unresolved(
                    location, trefi.target_module)
                unresolved_module = self._map_module_identifier_to_module.get(trefi.target_module)
                # if unresolved module name was found, make report for missing import
                if unresolved_module:
                    yield ReportEntry.missing_import(
                        location, unresolved_module.module_identifier)
            elif not self._resolve_symbol(trefi.module, trefi.symbol_name, trefi.target_module):
                # create unresolved report for trefi symbol name
                yield ReportEntry.unresolved(
                    trefi, os.path.join(str(trefi.target_module), trefi.symbol_name))
                # gather set of modules of symis with the same name as the trefi
                possible_required_modules = set(
                    symbol.module for symbol in self.symbols()
                    if symbol.symbol_name == trefi.symbol_name)
                for required_module in possible_required_modules:
                    yield ReportEntry.missing_import(trefi, required_module)

        # report undefined defis
        for defi in document.defis:
            if not self._resolve_symbol(defi.module, defi.symbol_name):
                yield ReportEntry.unresolved(
                    defi, os.path.join(str(defi.module), defi.symbol_name))

        # report tag matches
        if document.file in self.tags:
            for module, name, locations in self._get_possible_trefi_matches(document):
                yield ReportEntry.tag_match(locations, module=module, symbol_name=name)

    def _make_document_module_report(self, document: Document) -> Iterator[ReportEntry]:
        # report module name in file and environment mismatch
        if document.module.module_and_file_name_mismatch:
            yield ReportEntry.module_name_mismatch(document.module)

        # check gimports resolveable
        for gimport in document.gimports:
            if not self._resolve_module(document.module_identifier, gimport.imported_module):
                yield ReportEntry.unresolved(gimport, gimport.imported_module)
            else:
                for lang, binding in self._map_module_identifier_to_bindings.get(str(document.module_identifier), {}).items():
                    for trefi in binding.trefis:
                        if trefi.target_module == gimport.imported_module:
                            break
                    else:
                        yield ReportEntry.unused_import(
                            gimport, unused_module=gimport.imported_module, lang=binding.binding.lang)

        # report that this module has no language bindings
        if str(document.module_identifier) not in self._map_module_identifier_to_bindings:
            yield ReportEntry.no_bindings(document.module)

        # report redundant imports
        for redundant, sources in self.import_graph.redundant.get(str(document.module_identifier), {}).items():
            location = document.get_import_location(redundant)
            for source in sources:
                yield ReportEntry.redundant(location, redundant_module_name=source)

        # report duplicate imports
        for duplicate, locations in self.import_graph.duplicates.get(str(document.module_identifier), {}).items():
            for location in locations:
                yield ReportEntry.duplicate(location, symbol_name=duplicate)

        # report cyclic imports
        for cycle_causing_module, others in self.import_graph.cycles.get(str(document.module_identifier), {}).items():
            location = document.get_import_location(cycle_causing_module)
            if location:
                yield ReportEntry.cycle(location, cycle_causing_module, others=others)

    def _make_document_report(self, document: Document) -> Iterator[ReportEntry]:
        # report exceptions of the document
        for e in document.exceptions:
            message = str(e)
            location = document.file
            match = re.match(r'^"?(\s*)"?:(\d+):(\d+)', message)
            if match:
                pos1 = Position(int(match.group(2)), int(match.group(3)))
                pos2 = Position(pos1.line, pos1.column + 1)
                location = Location(match.group(1), Range(pos1, pos2))
            yield ReportEntry.error(location, message=message)

        # report duplicate definition errors generated during linking
        yield from self._duplicate_definition_report.get(document.file, ())

        if document.binding:
            yield from self._make_document_binding_report(document)
        elif document.module:
            yield from self._make_document_module_report(document)

    def _get_possible_trefi_matches(
            self, document: Document) -> List[Tuple[Union[ModuleIdentifier, str], str, List[Location]]]:
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

    def _resolve_module(
            self, module: Union[ModuleIdentifier, str], target: ModuleIdentifier) -> Optional[ModuleDefinitonSymbol]:
        """ Resolves the location of target module given the current module """
        if str(target) not in self._map_module_identifier_to_module:
            return None
        if str(target) in self.import_graph.reachable_modules_of(str(module)):
            return self._map_module_identifier_to_module[str(target)].module

    def _resolve_symbol(self,
                        module: ModuleIdentifier,
                        symbol_name: str,
                        symbol_module: Optional[ModuleIdentifier] = None) -> Optional[Symbol]:
        """ Resolves a symbol definition given the current module, the symbol name
            and an optional hint of the module that contains the symbol """
        target_module = symbol_module or module
        if str(symbol_module) != str(module) and not self._resolve_module(module, target_module):
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
        """ Returns the module and symbol name of a sym, def or tref at the given position """
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
        """ Checks if file is linked """
        return self._map_file_to_document.get(file) is not None

    def _unlink(self, file: str, silent: bool = False):
        """ Deletes all symbols/links provided by the file if tracked. """
        if file in self.tags:
            del self.tags[file]

        if file in self._duplicate_definition_report:
            del self._duplicate_definition_report[file]

        document = self._map_file_to_document.get(file)

        module_id = str(document.module_identifier)

        if document.binding:
            del self._map_module_identifier_to_bindings[module_id][document.binding.lang]
            if not self._map_module_identifier_to_bindings[module_id]:
                del self._map_module_identifier_to_bindings[module_id]
            if document.file in self.tags:
                del self.tags[document.file]
            if document.file in self.possible_trefis:
                del self.possible_trefis[document.file]
            if not silent:
                print('-BINDING', document.binding.lang, module_id)
        elif document.module:
            self.import_graph.remove(document.module_identifier)
            del self._map_module_identifier_to_module[module_id]
            if not silent:
                print('-MODULE', module_id)

        del self._map_file_to_document[file]
        if not silent:
            print('-FILE', file)

    def _link(self, document: Document, silent: bool = False):
        """ Starts tracking a doicument. Indexes links and symbols provided by it. """
        assert not self._is_linked(document.file), "Duplicate link"
        module = str(document.module_identifier)
        if document.binding:
            if document.binding.lang in self._map_module_identifier_to_bindings.get(module, ()):
                self._duplicate_definition_report.setdefault(document.file, [])
                self._duplicate_definition_report[document.file].append(
                    ReportEntry(
                        document.binding,
                        'duplicate_definition',
                        previous_definition=(
                            self._map_module_identifier_to_bindings[module][document.binding.lang].binding)))
                return
            self._map_module_identifier_to_bindings.setdefault(module, {})
            self._map_module_identifier_to_bindings[module][document.binding.lang] = document
            if self.tagger and document.binding.lang in ('en', 'lang'):
                self.tags[document.file] = self.tagger.predict(document.file)
            if not silent:
                print("+BINDING", module, document.binding.lang, os.path.basename(document.file))
        elif document.module:
            if module in self._map_module_identifier_to_module:
                self._duplicate_definition_report.setdefault(document.file, [])
                self._duplicate_definition_report[document.file].append(
                    ReportEntry(
                        document.module,
                        'duplicate_definition',
                        previous_definition=(
                            self._map_module_identifier_to_module[module].module)))
                return
            self._map_module_identifier_to_module[module] = document
            self.import_graph.add(document)
            if not silent:
                print("+MODULE", module, os.path.basename(document.file))

        self._map_file_to_document[document.file] = document
        if not silent:
            print('+FILE', document.file)

    def __init__(self):
        self._file_watcher = FileWatcher(['.tex'])
        self._watched_directories: List[str] = []

        self._map_file_to_document: Dict[str, Document] = dict()
        self._map_module_identifier_to_bindings: Dict[str, Dict[str, Document]] = dict()
        self._map_module_identifier_to_module: Dict[str, Document] = dict()

        self.import_graph = ImportGraph()
        self._duplicate_definition_report: Dict[str, List[ReportEntry]] = dict()

        self.tagger_path: Optional[str] = None
        self.tagger: Optional[seq2seq.Model] = None
        self.tags: Dict[str, object] = dict()
        # dict of file to list of possible trefis (module, name, token locations to wrap)
        self.possible_trefis: Dict[str, List[Tuple[ModuleIdentifier, str, List[Location]]]] = dict()

    def __getstate__(self):
        return (
            self._file_watcher,
            self._watched_directories,
            self._map_file_to_document,
            self._map_module_identifier_to_bindings,
            self._map_module_identifier_to_module,
            self.import_graph,
            self._duplicate_definition_report,
            self.tagger_path,
            self.tags,
            self.possible_trefis,
        )

    def __setstate__(self, state):
        # initialize other state
        self.tagger = None

        # load state
        (self._file_watcher,
         self._watched_directories,
         self._map_file_to_document,
         self._map_module_identifier_to_bindings,
         self._map_module_identifier_to_module,
         self.import_graph,
         self._duplicate_definition_report,
         self.tagger_path,
         self.tags,
         self.possible_trefis,) = state


class ReportEntry:
    def __init__(self, location: Union[Location, str], entry_type: str, **kwargs):
        if isinstance(location, str):
            location = Location(location, Range(Position(1, 1), Position(1, 1)))
        self.location = location
        self.entry_type = entry_type
        self.__dict__.update(kwargs)

    @staticmethod
    def unresolved(location: Union[Location, str], unresolved_symbol_or_module_name: str):
        return ReportEntry(location, 'unresolved', symbol=str(unresolved_symbol_or_module_name))

    @staticmethod
    def redundant(location: Union[Location, str], redundant_module_name: Union[ModuleIdentifier, str]):
        return ReportEntry(location, 'redundant', module=str(redundant_module_name))

    @staticmethod
    def missing_import(location: Union[Location, str], missing_module: Union[ModuleIdentifier, str]):
        return ReportEntry(location, 'missing_import', module=str(missing_module))

    @staticmethod
    def tag_match(
            locations: List[Union[Location, str]],
            module: Union[ModuleIdentifier, str],
            symbol_name: Union[ModuleIdentifier, Symbol, str]):
        return ReportEntry(
            Location.reduce_union(locations), 'match', module=str(module), name=str(symbol_name), tokens=locations)

    @staticmethod
    def unused_import(location: Union[Location, str], unused_module: Union[ModuleIdentifier, str], lang: str):
        return ReportEntry(location, 'unused', module=str(unused_module), lang=lang)

    @staticmethod
    def no_bindings(module: ModuleDefinitonSymbol):
        return ReportEntry(module, 'no_bindings', module_name=module.module_name)

    @staticmethod
    def duplicate(
            location: Union[Location, str],
            symbol_name: Union[ModuleIdentifier, Symbol, str]):
        return ReportEntry(location, 'duplicate', symbol_name=str(symbol_name))

    @staticmethod
    def cycle(location: Union[Location, str],
              cycle_causing_module: Union[ModuleIdentifier, str],
              others: List[Union[ModuleIdentifier, str]]):
        return ReportEntry(location, 'cycle', module=str(cycle_causing_module), others=list(map(str, others)))

    @staticmethod
    def error(location: Union[Location, str], message: Union[Exception, str]):
        return ReportEntry(location, 'error', message=str(message))

    @staticmethod
    def module_name_mismatch(location: Union[Location, str]):
        return ReportEntry(location, 'module_name_mismatch')

    @staticmethod
    def binding_lang_mismatch(location: Union[Location, str]):
        return ReportEntry(location, 'binding_lang_mismatch')

    @staticmethod
    def syntax_error(location: Union[Location, str], message: str, symbol: object):
        return ReportEntry(location, 'syntax_error', message=message)
