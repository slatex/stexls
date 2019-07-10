from __future__ import annotations
from typing import List, Dict, Optional, Iterator, Set, Iterable
import os
import itertools
import multiprocessing
import difflib
import re
import sys
from functools import partial

from trefier.misc.location import Position, Range, Location
from trefier.misc.file_watcher import FileWatcher
from trefier.models import seq2seq

from trefier.linting.exceptions import LinterException
from trefier.linting.identifiers import *
from trefier.linting.symbols import *
from trefier.linting.document import *
from trefier.linting.imports import ImportGraph

__all__ = ['Linter']


class Linter:
    def __init__(self):
        self._file_watcher = FileWatcher(['.tex'])
        self._watched_directories: List[str] = []

        self._map_file_to_document: Dict[str, Document] = dict()
        self._map_module_identifier_to_bindings: Dict[str, Dict[str, Document]] = dict()
        self._map_module_identifier_to_module: Dict[str, Document] = dict()
        self._symbol_index: Dict[str, List[SymiSymbol]] = dict()

        self.import_graph = ImportGraph()
        self._duplicate_definition_report: Dict[str, List[ReportEntry]] = dict()

        # currently loaded path to tagger
        self.tagger_path: Optional[str] = None
        # tagger path loaded by __setstate__
        self._last_tagger_path: Optional[str] = None
        # loaded tagger instance
        self.tagger: Optional[seq2seq.Model] = None
        # tags of the current tagger: Delete if None
        self.tags: Dict[str, object] = dict()

        self._last_update_report = None

        self.changed = False

    def __getstate__(self):
        return (
            self._file_watcher,
            self._watched_directories,
            self._map_file_to_document,
            self._map_module_identifier_to_bindings,
            self._map_module_identifier_to_module,
            self._symbol_index,
            self.import_graph,
            self._duplicate_definition_report,
            self.tags,
            self.tagger_path
        )

    def __setstate__(self, state):
        # initialize other state
        self.tagger = None
        self.tagger_path = None
        self._last_update_report = None
        self.changed = False

        # load state
        (self._file_watcher,
         self._watched_directories,
         self._map_file_to_document,
         self._map_module_identifier_to_bindings,
         self._map_module_identifier_to_module,
         self._symbol_index,
         self.import_graph,
         self._duplicate_definition_report,
         self.tags,
         self._last_tagger_path) = state

    def load_tagger_model(self, path: str):
        path = os.path.abspath(path)
        if seq2seq.Seq2SeqModel.verify_loadable(path):
            tagger = seq2seq.Seq2SeqModel.load(path)
            print(f'loading tagger from {path}: previous {self._last_tagger_path}', file=sys.stderr)
            # update tags if the loaded tagger is new,
            # or if the new tagger is different from the old tagger
            if not self._last_tagger_path or self._last_tagger_path != path:
                # update tags only if a new tagger was adder or the tagger is different from last time
                self.tags = dict()
                self.changed = True
                for binding in self.bindings():
                    if binding.lang in ('en', 'lang'):
                        print(f'TAGGING {os.path.basename(binding.file)}', file=sys.stderr)
                        self.tags[binding.file] = tagger.predict(binding.file)
            self._last_tagger_path = path
            self.tagger_path = path
            self.tagger = tagger
        else:
            raise LinterInternalException.create(f'Failed to load tagger from {path}')

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

    def goto_definition(self, file: str, line: int, column: int) -> Optional[Union[ModuleDefinitonSymbol, SymiSymbol]]:
        doc = self._map_file_to_document.get(file)
        if doc is None:
            raise LinterException("File not tracked")
        return (self._module_at_position(file, line, column)
                or self._named_symbol_at_position(file, line, column))

    def goto_implementation(self, file: str, line: int, column: int) -> List[Symbol]:
        definition = self.goto_definition(file, line, column)
        implementations = []
        if definition is not None:
            for _, binding in self._map_module_identifier_to_bindings.get(str(definition.module), {}).items():
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
            for parent_module in self.import_graph.parents_of(definition.module):
                for binding in self._map_module_identifier_to_bindings.get(parent_module, {}).values():
                    if isinstance(definition, ModuleDefinitonSymbol) and binding.module_identifier == definition.module:
                        references.append(binding.binding)
                    for symbol in itertools.chain(binding.trefis, binding.defis):
                        if isinstance(definition, SymiSymbol):
                            if self._resolve_symbol(symbol) == definition:
                                if isinstance(symbol, TrefiSymbol) and symbol.target_symbol_location:
                                    references.append(symbol.target_symbol_location)
                                elif isinstance(symbol, DefiSymbol) and symbol.name_argument_location:
                                    references.append(symbol.name_argument_location)
                                else:
                                    references.append(symbol)
                        elif isinstance(definition, ModuleDefinitonSymbol):
                            if self._resolve_target_module_identifier(symbol) == definition.module:
                                if isinstance(symbol, TrefiSymbol) and symbol.target_module:
                                    references.append(symbol.target_module_location)
                                else:
                                    references.append(symbol)
        return references

    def add(self, directory: os.PathLike):
        """ Adds a single directory to watched directory list.
            Returns True if watched directory list changed, returns False otherwise. """
        if os.path.isdir(directory):
            if directory not in self._watched_directories:
                self._watched_directories.append(directory)
                self.changed = True
                return True
        return False

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
               silent: bool = True,
               debug: bool = False):
        deleted, modified = self._update_watched_directories()

        # set changed flag
        self.changed |= bool(modified or deleted or not(self.tagger and self.tags))

        # remove tags if no tagger specified
        if not self.tagger and self.tags:
            self.tags = dict()
            self.tagger_path = None

        if not (deleted or modified):
            return dict(self.make_report(self._map_file_to_document.values()))

        # remove changed files
        if not silent: print('UNLINKING', file=sys.stderr, flush=True)
        for file in itertools.chain(deleted, modified):
            if self._is_linked(file):
                self._unlink(file, silent=False if debug else silent)

        # Parse all files in parallel or sequential
        documents = []
        if use_multiprocessing and not debug:
            with multiprocessing.Pool(n_jobs) as pool:
                for d in pool.imap_unordered(Document, modified):
                    if not silent: print(f'PARSED {os.path.basename(d.file)}', file=sys.stderr, flush=True)
                    documents.append(d)
        else:
            for d in map(partial(Document, ignore_exceptions=not debug), modified):
                if not silent: print(f'PARSED {os.path.basename(d.file)}', file=sys.stderr, flush=True)
                documents.append(d)

        # link successfully compiled documents
        if not silent: print('LINKING', file=sys.stderr, flush=True)
        for document in filter(lambda doc: doc.success, documents):
            self._link(document, silent=False if debug else silent)

        self.import_graph.update()

        report: Dict[str, Optional[List[ReportEntry]]] = dict(self.make_report(self._map_file_to_document.values()))

        # add reports for documents that failed to parse this time
        report.update(dict(self.make_report(filter(lambda doc: not doc.success, documents))))

        # set all other unhandled files to None in order to mark them as deleted
        for unhandled in itertools.chain(deleted, modified):
            report.setdefault(unhandled)

        return report
    
    def get_object_range_at_position(self, file: str, line: int, column: int) -> Optional[Range]:
        """ Returns the range of any type of object at the specified position in a file
            or None if no object is under the cursor. """
        document = self._map_file_to_document.get(file)
        if not document:
            raise Exception("File not tracked")

        position = Position(line, column)

        if document.module and document.module.range.contains(position):
            return document.module.range
        
        if document.binding and document.binding.range.contains(position):
            return document.binding.range
        
        for symbol in itertools.chain(document.trefis, document.defis, document.symis):
            if isinstance(symbol, TrefiSymbol):
                if symbol.target_module_location and symbol.target_module_location.contains(position):
                    return symbol.target_module_location.range
                if symbol.target_symbol_location and symbol.target_symbol_location.contains(position):
                    return symbol.target_symbol_location.range
            elif isinstance(symbol, DefiSymbol):
                if symbol.name_argument_location and symbol.name_argument_location.contains(position):
                    return symbol.name_argument_location.range
            elif isinstance(symbol, GimportSymbol):
                if symbol.imported_module_location and symbol.imported_module_location.contains(position):
                    return symbol.imported_module_location.range
            if symbol.contains(position):
                return symbol.range
        return None

    def make_report(self, documents: Iterable[Document], show_progress: bool = True) -> Iterator[Tuple[str, List[ReportEntry]]]:
        """ Iterates through the given documents and creates a a tuple of (file path, file report)
            for every file. """
        for document in documents:
            if show_progress: print(f'REPORT {os.path.basename(document.file)}', file=sys.stderr, flush=True)
            yield (document.file, list(self._make_document_report(document)))

    def _documents_in_module(self, module: Union[ModuleIdentifier, str]) -> Iterator[Document]:
        """ Returns an iterator for all files assigned to that module """
        module_document = self._map_module_identifier_to_module.get(str(module))
        if module_document:
            yield module_document
        yield from self._map_module_identifier_to_bindings.get(module, {}).values()

    def _resolve_target_module_identifier(
            self, symbol: Union[TrefiSymbol, DefiSymbol, GimportSymbol]) -> Optional[ModuleIdentifier]:
        """ Resolves the module identifier the given symbol "targets".
            E.g.: trefi[target?...]{...}, gimport{target}. Defis target the own file's module. """
        if isinstance(symbol, TrefiSymbol):
            if symbol.target_module is None:
                return symbol.module
            else:
                found = list(self.import_graph.find_module(symbol.target_module, symbol.module))
                if len(found) > 1:
                    raise LinterException(f'{symbol} Ambiguous import of "{symbol.target_module}": Found {found}')
                return next(iter(found), None)
        elif isinstance(symbol, DefiSymbol):
            return symbol.module
        elif isinstance(symbol, GimportSymbol):
            return symbol.imported_module
        else:
            raise Exception(f'Target module for {type(symbol)} is undefined')

    def _make_document_binding_report(self, document: Document) -> Iterator[ReportEntry]:
        """ Makes the report for a binding """
        # check wether the module of the filename matches environment
        if document.binding.module_and_file_name_mismatch:
            yield ReportEntry.module_name_mismatch(document.binding)

        # check wether the language of the filename matches the environment
        if document.binding.module_lang_and_file_name_lang_mismatch:
            yield ReportEntry.binding_lang_mismatch(document.binding)

        # report module defined
        if str(document.module_identifier) not in self._map_module_identifier_to_module:
            yield ReportEntry.unresolved(document.binding, str(document.module_identifier), 'module')
        else:
            # report undefined symbols
            # but do not report symbols if the module was not resolved
            for symbol in itertools.chain(document.trefis, document.defis):
                if not self._resolve_symbol(symbol):
                    if isinstance(symbol, TrefiSymbol):
                        child_modules = self.import_graph.reachable_modules_of(symbol.module)
                        target_module = self._resolve_target_module_identifier(symbol)
                        if not target_module:
                            assert symbol.target_module
                            yield ReportEntry.unresolved(
                                symbol.target_module_location or symbol,
                                symbol.target_module,
                                'module')
                            for missing_module in self.import_graph.find_module(symbol.target_module):
                                yield ReportEntry.missing_import(
                                    symbol.target_module_location or symbol,
                                    missing_module)
                        else:
                            yield ReportEntry.unresolved(
                                symbol.target_symbol_location or symbol,
                                str(target_module) + '/' + symbol.symbol_name,
                                'symbol')
                            for sym in self.symbols():
                                if sym.symbol_name == symbol.symbol_name and str(sym.module) not in child_modules:
                                    yield ReportEntry.missing_import(symbol, sym.module)
                    else:
                        yield ReportEntry.unresolved(symbol, symbol.symbol_name, 'symbol')

            # report if the binding uses the module
            if self._check_module_unused(document, document.module_identifier):
                yield ReportEntry.unused_import(document.binding, document.module_identifier)

            # report if a imported module is unused by this binding
            for gimport in self._map_module_identifier_to_module[str(document.module_identifier)].gimports:
                imported_module = self._resolve_symbol(gimport)
                if imported_module:
                    assert isinstance(imported_module, ModuleDefinitonSymbol)
                    if self._check_module_unused(document, imported_module.module):
                        yield ReportEntry.unused_import(document.binding, imported_module.module)

        # report tag matches
        for module, name, ranges in self._get_possible_trefi_matches(document):
            yield ReportEntry.tag_match(ranges, module_name=module.module_name, symbol_name=name)

    def _check_module_unused(self, document: Document, module: ModuleIdentifier) -> bool:
        """ Returns True if the given module identifier is not used in any trefi import of the document. """
        for symbol in document.trefis:
            if self._resolve_target_module_identifier(symbol) == module:
                return False
        return True

    def _resolve_symbol(
            self, symbol: Union[TrefiSymbol, DefiSymbol, GimportSymbol]) -> Optional[Union[SymiSymbol, ModuleDefinitonSymbol]]:
        """ Resolves the target symbol of trefis, defis and gimports """
        target_module = self._resolve_target_module_identifier(symbol)
        if target_module:
            if isinstance(symbol, GimportSymbol):
                module_definition = self._map_module_identifier_to_module.get(str(target_module))
                if module_definition:
                    return module_definition.module
            else:
                return self._resolve_symbol_name_in_module(symbol.symbol_name, target_module)
    
    def _report_unresolved_or_unused_imports(self, gimports: Iterable[GimportSymbol]) -> Iterable[ReportEntry]:
        # check gimports resolveable
        for gimport in gimports:
            if not self._resolve_symbol(gimport):
                yield ReportEntry.unresolved(gimport, gimport.imported_module, 'module')
            else:
                module = str(gimport.module)
                for binding in self._map_module_identifier_to_bindings.get(
                        module, {}).values():
                    if self._check_module_unused(binding, gimport.imported_module):
                        break
                else:
                    yield ReportEntry.unused_import(
                        gimport, unused_module=gimport.imported_module)
    
    def _report_redundant_imports(self, document: Document) -> Iterable[ReportEntry]:
        for redundant, sources in self.import_graph.redundant.get(str(document.module_identifier), {}).items():
            location = document.get_import_location(redundant)
            for source in sources:
                yield ReportEntry.redundant(location, redundant_module_name=source)

    def _make_document_module_report(self, document: Document) -> Iterator[ReportEntry]:
        # report module name in file and environment mismatch
        if document.module.module_and_file_name_mismatch:
            yield ReportEntry.module_name_mismatch(document.module)

        yield from self._report_unresolved_or_unused_imports(document.gimports)

        # report that this module has no language bindings
        if str(document.module_identifier) not in self._map_module_identifier_to_bindings:
            yield ReportEntry.no_bindings(document.module)

        # report redundant imports
        yield from self._report_redundant_imports(document)

        # report duplicate imports
        for duplicate, locations in self.import_graph.duplicates.get(str(document.module_identifier), {}).items():
            for location in locations:
                yield ReportEntry.duplicate(location, symbol=duplicate, symbol_type='module')

        # report cyclic imports
        for cycle_causing_module, others in self.import_graph.cycles.get(str(document.module_identifier), {}).items():
            location = document.get_import_location(cycle_causing_module)
            if location:
                yield ReportEntry.cycle(location, cycle_causing_module, others=others)

    def _make_document_report(self, document: Document) -> Iterator[ReportEntry]:
        # report exceptions of the document
        for range, message in document.exception_summary:
            yield ReportEntry.error(range, message=message)

        if document.syntax_errors:
            for syntax_error_location, msg in document.syntax_errors.items():
                yield ReportEntry.syntax_error(syntax_error_location, message=msg)

        # report duplicate definition errors generated during linking
        yield from self._duplicate_definition_report.get(document.file, ())

        if document.binding:
            yield from self._make_document_binding_report(document)
        elif document.module:
            yield from self._make_document_module_report(document)

    def _get_possible_trefi_matches(
            self, document: Document) -> List[Tuple[ModuleIdentifier, str, List[Range]]]:
        """ Looks at the tags for a document and returns possibly matching symbols with the
            source location of the matching tokens.
            :returns List of tuples of (module of match, symbol name of match, List of source tokens in the file) """
        matches = []
        tags = self.tags.get(document.file)
        if tags:
            pred, token_ranges, tokens, envs = tags
            for is_keyword, group in itertools.groupby(enumerate(pred > 0.5), key=lambda x: x[1]):
                if not is_keyword:
                    continue
                indices, values = zip(*group)
                ranges = [
                    Range(
                        Position(token_ranges[i][0][0], token_ranges[i][0][1]),
                        Position(token_ranges[i][1][0], token_ranges[i][1][1])
                    ) for i in indices
                ]
                name = '-'.join(tokens[i] for i in indices)
                for similarity, symi in self._find_similarly_named_symbols(name):
                    matches.append((symi.module, symi.symbol_name, ranges))
        return matches

    def _find_similarly_named_symbols(self, name: str, threshold: float = 0) -> Iterator[Tuple[float, SymiSymbol]]:
        """ Finds all symbols which name's are equal or similar to the given name """
        if len(name) > 4 and threshold and 0 < threshold <= 1:
            for symbol_name, symis in self._symbol_index.items():
                ratio = difflib.SequenceMatcher(a=symbol_name, b=name).ratio()
                if ratio > threshold:
                    for symi in symis:
                        yield (ratio, symi)
        else:
            for symi in self._symbol_index.get(name, ()):
                yield (1, symi)

    def _resolve_symbol_name_in_module(
            self,
            symbol_name: str,
            module: Union[ModuleIdentifier, str]) -> Optional[SymiSymbol]:
        """ Resolves a symbol name to a symi from the given module or None if the symbol_name is not in the module. """
        document = self._map_module_identifier_to_module.get(str(module))
        if document:
            for sym in document.symis:
                if sym.symbol_name == symbol_name:
                    return sym
        return None

    def _module_at_position(self, file: str, line: int, column: int) -> Optional[ModuleDefinitonSymbol]:
        doc = self._map_file_to_document.get(file)
        if doc is None:
            raise Exception("File not tracked")

        position = Position(line, column)

        if doc.module is not None:
            if doc.module.range.contains(position):
                return doc.module

        if doc.binding is not None:
            if doc.binding.range.contains(position):
                module_document: Optional[Document] = self._map_module_identifier_to_module.get(str(doc.module_identifier))
                if module_document:
                    return module_document.module
                else:
                    return

        for trefi in doc.trefis:
            if trefi.target_module_location is not None:
                if trefi.target_module_location.range.contains(position):
                    module_document: Optional[Document] = self._map_module_identifier_to_module.get(
                        str(self._resolve_target_module_identifier(trefi)))
                    if module_document:
                        return module_document.module
                    else:
                        return

        for gimport in doc.gimports:
            if gimport.imported_module_location.range.contains(position):
                module_document: Optional[Document] = self._map_module_identifier_to_module.get(
                    str(self._resolve_target_module_identifier(gimport)))
                if module_document:
                    return module_document.module
                else:
                    return

        return None

    def _named_symbol_at_position(self, file: str, line: int, column: int) -> Optional[SymiSymbol]:
        """ Returns the module and symbol name of a sym, def or tref at the given position """
        doc = self._map_file_to_document.get(file)
        if doc is None:
            raise Exception("File not tracked")
        position = Position(line, column)

        if doc.module:
            for symi in doc.symis:
                if symi.name_contains(position):
                    return symi
        elif doc.binding:
            for trdefi in itertools.chain(doc.trefis, doc.defis):
                for loc in trdefi.symbol_name_locations:
                    if loc.range.contains(position):
                        return self._resolve_symbol(trdefi)
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

        document: Document = self._map_file_to_document[file]

        module_id = str(document.module_identifier)

        if document.binding:
            if not silent:
                print('-BINDING', document.binding.lang, module_id, file=sys.stderr)
            del self._map_module_identifier_to_bindings[module_id][document.binding.lang]
            if not self._map_module_identifier_to_bindings[module_id]:
                del self._map_module_identifier_to_bindings[module_id]
            if document.file in self.tags:
                del self.tags[document.file]
        elif document.module:
            if not silent:
                print('-MODULE', module_id, file=sys.stderr)
            for sym in document.symis:
                self._symbol_index[sym.symbol_name].remove(sym)
                if not self._symbol_index[sym.symbol_name]:
                    del self._symbol_index[sym.symbol_name]
            self.import_graph.remove(document.module_identifier)
            del self._map_module_identifier_to_module[module_id]

        del self._map_file_to_document[file]
        if not silent:
            print('-FILE', file, file=sys.stderr)

    def _link(self, document: Document, silent: bool = False):
        """ Starts tracking a document. Indexes links and symbols provided by it. """
        assert not self._is_linked(document.file), "Duplicate link"
        module = str(document.module_identifier)
        if document.binding:
            if document.binding.lang in self._map_module_identifier_to_bindings.get(module, ()):
                self._duplicate_definition_report.setdefault(document.file, [])
                self._duplicate_definition_report[document.file].append(
                    ReportEntry.duplicate(document.binding, symbol=document.binding))
                return
            if not silent:
                print("+BINDING", module, document.binding.lang, os.path.basename(document.file), file=sys.stderr)
            self._map_module_identifier_to_bindings.setdefault(module, {})
            self._map_module_identifier_to_bindings[module][document.binding.lang] = document
            if self.tagger and document.binding.lang in ('en', 'lang'):
                self.tags[document.file] = self.tagger.predict(document.file)
        elif document.module:
            if module in self._map_module_identifier_to_module:
                self._duplicate_definition_report.setdefault(document.file, [])
                self._duplicate_definition_report[document.file].append(
                    ReportEntry.duplicate(document.module, symbol=document.module))
                return
            if not silent:
                print("+MODULE", module, os.path.basename(document.file), file=sys.stderr)
            for sym in document.symis:
                self._symbol_index.setdefault(sym.symbol_name, [])
                self._symbol_index[sym.symbol_name].append(sym)
            self._map_module_identifier_to_module[module] = document
            self.import_graph.add(document)

        self._map_file_to_document[document.file] = document
        if not silent:
            print('+FILE', document.file, file=sys.stderr)

    def auto_complete(self, file: str, context: str) -> Iterator[dict]:
        """ Yields a named tuple of type {type: str, value: str} for each possible autocomplete item
        :param file: Current file
        :param context: Context that needs completions
        """
        document = self._map_file_to_document.get(file)

        if not document:
            raise Exception("File not tracked")

        yielded_values: Set[str] = set()

        # find trefis, reverse so that first match moves to the front
        for match in reversed(list(re.finditer(r'\\([ma]*)tref(i+)s?', context))):
            # remove irrelevant matches from context
            sub_context = context[match.span()[0]:]
            for trefi_module in re.finditer(r'\\[ma]*trefi+s?\s*\[\s*([\w\-]*)$', sub_context):
                for module in self.import_graph.reachable_modules_of(document.module_identifier):
                    if (self._map_module_identifier_to_module[module]
                            .module_identifier
                            .module_name).startswith(trefi_module.group(1)):
                        value = self._map_module_identifier_to_module[module].module_identifier.module_name
                        if value not in yielded_values:
                            yield {
                                'type': 'module',
                                'value': value
                            }
                            yielded_values.add(value)
                return

            for trefi_symbol in re.finditer(r'\\[ma]*trefi+s?\s*\[(.*?)\?([\w\-]*)$', sub_context):
                target_module_name = trefi_symbol.group(1) or document.module_identifier.module_name
                for target_module in self.import_graph.find_module(
                        target_module_name, document.module_identifier):
                    for symi in self._map_module_identifier_to_module[str(target_module)].symis:
                        if symi.symbol_name.startswith(trefi_symbol.group(2)):
                            value = symi.symbol_name
                            if value not in yielded_values:
                                yield {'type': 'symbol', 'value': value}
                                yielded_values.add(value)
                return
            # for trefi_text in re.finditer(r'\\[ma]*trefi+s?(?:\[(.*?)?(?:\?(.*?))?\])?\{(.*?)$', trefi_context):
            #     is_alt = 'a' in trefi_match.group(1)
            #     arg_count = len(trefi_match.group(2))
            #     return
            return

        for match in reversed(list(re.finditer(r'\\([ma]*)def(i+)s?', context))):
            # remove irrelevant matches from context
            sub_context = context[match.span()[0]:]
            for defi in re.finditer(
                    r'\\[ma]*defi+s?\s*\[(?:\s*[\w\-]+\s*=\s*[\w\-]+,)*\s*name\s*=\s*([\w\-]*)$', sub_context):
                defi_name = defi.group(1)
                for symi in self._map_module_identifier_to_module[str(document.module_identifier)].symis:
                    value = symi.symbol_name
                    if value not in yielded_values:
                        if symi.symbol_name.startswith(defi_name):
                            yield {'type': 'symbol', 'value': value}
                        yielded_values.add(value)
                return
            return

        for match in reversed(list(re.finditer(r'\\gimport', context))):
            # remove irrelevant matches from context
            sub_context = context[match.span()[0]:]
            for imported_module in re.finditer(r'\\gimport\s*(?:\[\s*(\w+/\w+)\s*\])?\s*{(.*?)$', sub_context):
                identifier = (imported_module.group(1) or document.module_identifier.without_name) + "/" + imported_module.group(2)
                for module in self.import_graph.graph:
                    if module.startswith(identifier):
                        value = self._map_module_identifier_to_module[module].module_identifier.module_name
                        if value not in yielded_values:
                            yield {
                                'type': 'module',
                                'value': value
                            }
                            yielded_values.add(value)
                return

            for imported_module in re.finditer(r'\\gimport\s*\[\s*([\w\-/]*)$', sub_context):
                for module in self.import_graph.graph:
                    mod_id_part = self._map_module_identifier_to_module[module].module_identifier.without_name
                    if mod_id_part.startswith(imported_module.group(1)):
                        value = mod_id_part
                        if value not in yielded_values:
                            yield {'type': 'repository', 'value': value}
                            yielded_values.add(value)
                return
            return


class ReportEntry:
    def __init__(self, range: Range, entry_type: str, **kwargs):
        assert range is not None
        if isinstance(range, str):
            range = Range(Position(1, 1), Position(1, 1))
        self.range = range
        self.entry_type = entry_type
        self.__dict__.update(kwargs)

    @staticmethod
    def unresolved(location: Location, unresolved_symbol_or_module_name: str, symbol_type: str):
        return ReportEntry(location.range,
                           'unresolved',
                           symbol=str(unresolved_symbol_or_module_name),
                           symbol_type=symbol_type)

    @staticmethod
    def redundant(location: Location, redundant_module_name: Union[ModuleIdentifier, str]):
        return ReportEntry(location.range, 'redundant', module=str(redundant_module_name))

    @staticmethod
    def missing_import(location: Location, missing_module: Union[ModuleIdentifier, str]):
        return ReportEntry(location.range, 'missing_import', module=str(missing_module))

    @staticmethod
    def tag_match(
            ranges: List[Range],
            module_name: str,
            symbol_name: Union[ModuleIdentifier, Symbol, str]):
        return ReportEntry(Range.reduce_union(ranges),
                           'match', module=module_name, name=str(symbol_name), tokens=ranges)

    @staticmethod
    def unused_import(location: Location, unused_module: Union[ModuleIdentifier, str]):
        return ReportEntry(location.range, 'unused', module=str(unused_module))

    @staticmethod
    def no_bindings(module: ModuleDefinitonSymbol):
        return ReportEntry(module.range, 'no_bindings', module_name=module.module_name)

    @staticmethod
    def duplicate(
            location: Location,
            symbol: Union[ModuleIdentifier, Symbol, ModuleDefinitonSymbol, ModuleBindingDefinitionSymbol, str],
            symbol_type: Optional[str] = None):
        if isinstance(symbol, SymiSymbol):
            symbol = symbol.symbol_name
            symbol_type = 'symbol'
        elif isinstance(symbol, ModuleDefinitonSymbol):
            symbol = symbol.module
            symbol_type = 'module'
        elif isinstance(symbol, ModuleBindingDefinitionSymbol):
            symbol = symbol.module + '.' + symbol.lang
            symbol_type = 'binding'
        return ReportEntry(location.range, 'duplicate', symbol=str(symbol), symbol_type=symbol_type)

    @staticmethod
    def cycle(location: Location,
              cycle_causing_module: Union[ModuleIdentifier, str],
              others: List[Union[ModuleIdentifier, str]]):
        return ReportEntry(location.range, 'cycle', module=str(cycle_causing_module), others=list(map(str, others)))

    @staticmethod
    def error(range: Range, message: Union[Exception, str]):
        return ReportEntry(range, 'error', message=str(message))

    @staticmethod
    def module_name_mismatch(location: Location):
        return ReportEntry(location.range, 'module_name_mismatch')

    @staticmethod
    def binding_lang_mismatch(location: Location):
        return ReportEntry(location.range, 'binding_lang_mismatch')

    @staticmethod
    def syntax_error(location: Location, message: str):
        return ReportEntry(location.range, 'syntax_error', message=message)
