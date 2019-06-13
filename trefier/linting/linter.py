from __future__ import annotations
from typing import List, Dict, Union, Tuple, Callable
from glob import glob
import os
import re
import itertools
import numpy as np
import multiprocessing
import subprocess
import sys
import tempfile
from PIL import Image
import loguru

from trefier.misc.location import *
from trefier.misc.file_watcher import FileWatcher
from trefier.parser.latex_parser import LatexParser, Environment, Node


def _node_to_location(node: Node) -> Location:
    """ Helper that transforms a node to a location.Location object """
    return Location(node.parser.file, Range(Position(*node.begin_position), Position(*node.end_position)))


def _linter_range_to_Range(linter_range: Tuple[Tuple[int, int], Tuple[int, int]]) -> Range:
    """ Helper that transforms the linter range tuple into a location.Range object """
    return Range(Position(*linter_range[0]),Position(*linter_range[1]))


class LinterException(Exception):
    pass


class LinterArgumentCountException(LinterException):
    @staticmethod
    def create(location: Location, expected: Union[int, str], found: int) -> LinterArgumentCountException:
        return LinterArgumentCountException(
            f'{location} Expected were {expected} argument(s) (found {found} argument(s))')


class LinterGimportModuleFormatException(LinterException):
    @staticmethod
    def create(location: Location, found: str) -> LinterGimportModuleFormatException:
        return LinterGimportModuleFormatException(f'{location} Expected format is "a/b" (found "{found}")')


class LinterModuleFromFilenameException(LinterException):
    @staticmethod
    def create(filename: str) -> LinterModuleFromFilenameException:
        return LinterModuleFromFilenameException(
            f'Unable to extract module from filename "{filename}":'
            f'Expected filename format is .../<base>/<repository>/"source"/<module>')


class ModuleIdentifier:
    def __init__(self, base: str, repository_name: str, module_name: str):
        if not (base or repository_name or module_name):
            raise Exception(f'Module identifier arguments may not be falsy:'
                            f' "{base}", "{repository_name}", "{module_name}"')
        self.base = base
        self.repository_name = repository_name
        self.module_name = module_name

    def __repr__(self):
        return f'{self.base}/{self.repository_name}/{self.module_name}'

    def __hash__(self):
        return hash(self.base) ^ hash(self.repository_name) ^ hash(self.module_name)

    def __eq__(self, other: ModuleIdentifier):
        return self.base == other.base and self.repository_name == other.repository_name and self.module_name == other.module_name

    @staticmethod
    def from_file(file: str) -> ModuleIdentifier:
        parts = file.split('/')

        if parts[-2] != 'source' or len(parts) < 4:
            raise LinterModuleFromFilenameException.create(file)

        return ModuleIdentifier(
            base=parts[-4],
            repository_name=parts[-3],
            module_name=parts[-1].split('.')[0],
        )

    @staticmethod
    def from_id_string(id: str) -> ModuleIdentifier:
        parts = id.split('/')
        assert len(parts) == 3, "Invalid id string"
        return ModuleIdentifier(*parts)


class SymbolIdentifier:
    def __init__(self, symbol_name: str, module: ModuleIdentifier = None):
        """ An unique identifier for a symbol: base/repo/module/symbol """
        self.symbol_name = symbol_name
        self.module = module

    def __repr__(self):
        return f'{self.module}/{self.symbol_name}'


class Symbol(Location):
    def __init__(self, file: str, full_range: Range):
        """
        Symbol base
        :param file: File in which the symbol is located
        :param full_range: The full range of what parts of the file are part of this symbol
        """
        assert isinstance(full_range, Range)
        super().__init__(file, full_range)
        self.module = ModuleIdentifier.from_file(file)


class ModuleDefinitonSymbol(Symbol):
    MODULE_PATTERN = re.compile(r'modsig\*?')

    def __init__(self, module_name: str, file: str, full_range: Range):
        super().__init__(file, full_range)
        if module_name != self.module.module_name:
            raise LinterException(f'Module name inferred from the file name ({self.module.module_name})'
                                  f' does not match with the name ({module_name}) written in the environment ')

    @staticmethod
    def from_node(node: Environment) -> ModuleDefinitonSymbol:
        # assert that the node's name is 'modsig'
        if node.env_name != 'modsig':
            raise LinterException(f'{_node_to_location(node.name)}'
                                  f'Expected environment to have name "modsig" but found "{node.env_name}"')

        if len(node.rargs) != 1:
            raise LinterArgumentCountException.create(_node_to_location(node), "exactly 1", len(node.rargs))

        mod_name_arg: Node = node.rargs[0].remove_brackets()
        mod_name_arg_range: Range = _linter_range_to_Range(mod_name_arg.effective_range)

        module_name = mod_name_arg.text

        return ModuleDefinitonSymbol(module_name, node.parser.file, mod_name_arg_range)


class ModuleBindingDefinitionSymbol(Symbol):
    MODULE_BINDING_PATTERN = re.compile(r'mhmodnl\*?')

    def __init__(self, bound_module_name: str, lang: str, file: str, full_range: Range):
        super().__init__(file, full_range)
        self.lang = lang
        if bound_module_name != self.module.module_name:
            raise LinterException(f'Module name inferred from filename ({self.module.module_name})'
                                  f'does not match with the environment ({bound_module_name})')

    @staticmethod
    def from_node(node: Environment) -> ModuleBindingDefinitionSymbol:
        # assert that the node's name is 'mhmodnl'
        if node.env_name != 'mhmodnl':
            raise LinterException(f'{_node_to_location(node.name)}'
                                  f' Expected environment to have name "mhmodnl" but found "{node.env_name}"')

        if len(node.rargs) != 2:
            raise LinterArgumentCountException.create(_node_to_location(node), "exactly 2", len(node.rargs))

        # get the arg that contains the module
        module_rarg = node.rargs[0].remove_brackets()

        # get the effective range
        effective_range = module_rarg.effective_range

        # construct range
        assert len(effective_range) == 2
        module_range = Range(Position(*effective_range[0]), Position(*effective_range[1]))

        # get the argument where the language is stored
        lang_arg = node.rargs[1]

        # remove {} and ws to get only the language text
        binding_language = lang_arg.text[1:-1].strip()

        return ModuleBindingDefinitionSymbol(module_rarg.text.strip(), binding_language, node.parser.file, module_range)


class GimportSymbol(Symbol):
    GIMPORT_PATTERN = re.compile(r'gimport\*?')

    def __init__(self, imported_module_location: Location,
                 imported_module: ModuleIdentifier,
                 file: str,
                 full_range: Range):
        """ Gimport symbol \\gimport[imported_module.base/imported_module.repository]{imported_module.module_name} """
        super().__init__(file, full_range)
        self.imported_module_location = imported_module_location
        self.imported_module = imported_module

    @staticmethod
    def from_node(gimport: Environment, containing_module: ModuleIdentifier = None) -> GimportSymbol:
        location = _node_to_location(gimport)

        if len(gimport.rargs) != 1:
            args_location = (
                _node_to_location(gimport.rargs[0]).union(_node_to_location(gimport.rargs[-1]))
                if len(gimport.rargs) >= 1
                else location)
            raise LinterArgumentCountException.create(
                args_location, "exactly 1 target module name", len(gimport.rargs))

        imported_module_arg: Node = gimport.rargs[0].remove_brackets()
        imported_module_arg_range: Range = _linter_range_to_Range(imported_module_arg.effective_range)
        imported_module_name: str = imported_module_arg.text.strip()

        if len(gimport.oargs) > 1:
            raise LinterArgumentCountException.create(
                _node_to_location(gimport.oargs[0]), "up to 1 repository", len(gimport.oargs))

        if len(gimport.oargs) == 1:
            oarg = gimport.oargs[0]
            oarg_str: str = oarg.text[1:-1].strip()
            parts = list(oarg_str.split('/'))
            if len(parts) != 2 or not all(map(len, parts)):
                raise LinterGimportModuleFormatException.create(_node_to_location(oarg), oarg_str)
            return GimportSymbol(
                Location(location.file, imported_module_arg_range),
                ModuleIdentifier(*parts, imported_module_name),
                gimport.parser.file,
                location.range
            )

        containing_module = containing_module or ModuleIdentifier.from_file(gimport.parser.file)
        return GimportSymbol(
            Location(location.file, imported_module_arg_range),
            ModuleIdentifier(containing_module.base, containing_module.repository_name, imported_module_name),
            gimport.parser.file,
            location.range
        )


class EnvironmentSymbolWithStaticArgumentCount(Symbol):
    MASTER_PATTERN = re.compile(r'([ma]*)(sym|tref|def)(i+)s?\*?')

    def __init__(self,
                 symbol_name: str,
                 symbol_name_locations: List[Location],
                 search_terms: List[List[str]],
                 env_name: str,
                 file: str,
                 full_range: Range):
        """ Basic environment that has "i"s in it's name, indicating the number of arguments expected.
        :param symbol_name: Name of the symbol
        :param symbol_name_locations: List of locations of where the tokens are
            that should link to the symbol's name
        :param search_terms: List of lists of tokens that may
            be used to search for this symbol without knowing the exact "name".
        :param env_name: Name of the environment
        """
        super().__init__(file, full_range)
        self.symbol_name = symbol_name
        self.symbol_name_locations = symbol_name_locations
        self.search_terms = search_terms
        self.env_name = env_name
        match = EnvironmentSymbolWithStaticArgumentCount.MASTER_PATTERN.fullmatch(self.env_name)
        if not match:
            raise LinterException(f'{self} Invalid environment name "{env_name}"')
        self.is_alt = 'a' in match.group(1)

    @staticmethod
    def get_info(env: Environment) -> Tuple[str, List[Location], List[List[str]]]:
        """ Extracts vital information from symi, trefi and defi environments
        Extracts:
            - alt argument locations and search terms
            - argument locations and search terms
            - symbol name by concatenating arguments with "-"
            - asserts:
                - oarg count is either 0 or 1 for trefi and defi
                - oarg count is 0 for symi
                - if alt: rarg count >= 2
                - if !alt: rarg count >= 1
                - symi is never alt
        :returns Tuple of (name, name locations, search terms)
        """
        location = _node_to_location(env)

        match = EnvironmentSymbolWithStaticArgumentCount.MASTER_PATTERN.fullmatch(env.env_name)

        is_alt = 'a' in match.group(1)

        static_argument_count = len(match.group(3)) + int(is_alt)

        if not match:
            raise LinterException(f'{location} Invalid environment name encountered: "{env.env_name}"')

        if match.group(2) == 'sym' and is_alt:
            raise LinterException(f'{location} sym* environments must not be prefixed with "a" (found: {env.env_name})')

        if len(env.oargs) > 1:
            raise LinterArgumentCountException.create(_node_to_location(env.oargs[0]), "1 or 0", len(env.oargs))

        if len(env.rargs) == 0:
            raise LinterArgumentCountException.create(location, "at least 1 rarg", 0)

        if len(env.rargs) != static_argument_count:
            raise LinterArgumentCountException.create(
                _node_to_location(env.rargs[0]), static_argument_count, len(env.rargs))

        rargs = [rarg.remove_brackets() for rarg in env.rargs]
        rarg_locations = list(map(_node_to_location, rargs))
        search_terms: List[List[str]] = []
        symbol_name_locations = []

        if is_alt:
            symbol_name_locations.append(rarg_locations[0])
            search_terms.append([rargs[0].text.strip()])
            rargs = rargs[1:]
            rarg_locations = rarg_locations[1:]

        search_terms.append([rarg.text.strip() for rarg in rargs])
        symbol_name = '-'.join(search_terms[-1])
        symbol_name_locations.append(rarg_locations[0].union(rarg_locations[-1]))

        return symbol_name, symbol_name_locations, search_terms


class SymiSymbol(EnvironmentSymbolWithStaticArgumentCount):
    SYM_PATTERN = re.compile(r'symi+s?\*?')

    def __init__(self,
                 symbol_name: str,
                 symbol_name_locations: List[Location],
                 search_terms: List[List[str]],
                 env_name: str,
                 file: str,
                 full_range: Range):
        super().__init__(symbol_name, symbol_name_locations, search_terms, env_name, file, full_range)

    @staticmethod
    def from_node(symi: Environment):
        symbol_name, symbol_name_locations, search_terms = EnvironmentSymbolWithStaticArgumentCount.get_info(symi)

        location = _node_to_location(symi)

        return SymiSymbol(symbol_name, symbol_name_locations, search_terms,
                          symi.env_name, symi.parser.file, location.range)


class DefiSymbol(EnvironmentSymbolWithStaticArgumentCount):
    DEFI_PATTERN = re.compile(r'[ma]*defi+s?\*?')

    def __init__(self,
                 symbol_name: str,
                 symbol_name_locations: List[Location],
                 search_terms: List[List[str]],
                 env_name: str,
                 file: str,
                 full_range: Range):
        super().__init__(symbol_name, symbol_name_locations, search_terms, env_name, file, full_range)

    @staticmethod
    def from_node(defi: Environment) -> DefiSymbol:
        symbol_name, symbol_name_locations, search_terms = EnvironmentSymbolWithStaticArgumentCount.get_info(defi)

        location = _node_to_location(defi)

        if len(defi.oargs) == 1:
            oarg = defi.oargs[0].remove_brackets()
            pattern = re.compile(r'(name\s*=\s*)(.*?)(?:[$\s,\]]|$)')
            matches = list(re.finditer(pattern, oarg.text))
            if len(matches) != 1:
                raise LinterArgumentCountException.create(_node_to_location(oarg), 'exactly 1 "name="', len(matches))
            match = matches[0]
            symbol_name = match.group(2)
            oargbegin, oargend = list(oarg.split_range(pattern, keep_delimeter=True))[1]
            oargbegin += len(match.group(1))
            oargend = oargbegin + len(symbol_name)
            symbol_name_locations.insert(0, Location(defi.parser.file, Range(
                Position(*defi.parser.offset_to_position(oargbegin)),
                Position(*defi.parser.offset_to_position(oargend))
            )))

        return DefiSymbol(
            symbol_name, symbol_name_locations, search_terms,
            defi.env_name, defi.parser.file, location.range)


class TrefiSymbol(EnvironmentSymbolWithStaticArgumentCount):
    TREFI_PATTERN = re.compile(r'[ma]*trefi+s?\*?')

    def __init__(self,
                 target_module: ModuleIdentifier,
                 target_module_location: Location,
                 symbol_name: str,
                 symbol_name_locations: List[Location],
                 search_terms: List[List[str]],
                 env_name: str,
                 file: str,
                 full_range: Range):
        super().__init__(symbol_name, symbol_name_locations, search_terms, env_name, file, full_range)
        self.target_module = target_module
        self.target_module_location = target_module_location

    @staticmethod
    def from_node(trefi: Environment) -> TrefiSymbol:
        symbol_name, symbol_name_locations, search_terms = EnvironmentSymbolWithStaticArgumentCount.get_info(trefi)

        location = _node_to_location(trefi)

        target_module_identifier: ModuleIdentifier = ModuleIdentifier.from_file(trefi.parser.file)
        target_module_location: Location = None

        # get the module and optionally the symbol from an oarg if present
        if len(trefi.oargs) == 1:
            # get the token inside the oarg
            oarg = trefi.oargs[0].remove_brackets()

            # split on ?
            parts: List[Tuple[Tuple[int, int], Tuple[int, int], str]] = list(oarg.split_range(
                r'\?', as_position=True, return_lexemes=True))

            # must have at most 2 parts "a?b"
            if len(parts) > 2:
                raise Exception(f'{location} Expected a trefi argument of the format'
                                ' "[module]", "[module?name]" or "[?name]",'
                                f' but found "[{oarg.text}]"')

            # the last part must be defined. "?b" is allowed but "?" or "a?" is not.
            if not parts[-1][-1]:
                raise Exception(f'{_node_to_location(oarg)}'
                                f' Empty module or symbol name in trefi: "[{oarg.text}]"')

            # assign new module from oarg or inherit in case of "trefi[?name]"
            if len(parts) >= 1 and parts[0][-1]:
                target_module_identifier.module_name = parts[0][-1]
                target_module_location = Location(
                    trefi.parser.file,
                    Range(Position(*parts[0][0]), Position(*parts[0][1])))

            # if a 2nd part is defined, use it as target symbol
            if len(parts) == 2:
                symbol_name = parts[-1][-1]
                search_terms.append([symbol_name])
                target_symbol_location = Location(
                    trefi.parser.file,
                    Range(Position(*parts[-1][0]), Position(*parts[-1][1])))
                symbol_name_locations.insert(0, target_symbol_location)

        return TrefiSymbol(target_module_identifier, target_module_location,
                           symbol_name, symbol_name_locations, search_terms,
                           trefi.env_name, trefi.parser.file, location.range)


class Document:
    @property
    def module_identifier(self) -> ModuleIdentifier:
        if self.binding:
            return self.binding.module
        if self.module:
            return self.module.module

    def __init__(self, file: str):
        self.file = file
        self.exceptions: List[Exception] = []
        self.module: ModuleDefinitonSymbol = None
        self.binding: ModuleBindingDefinitionSymbol = None
        self.success = False
        parser = LatexParser(file)
        self.success = parser.success
        # dict of modules to modules it imports
        self.import_graph: Dict[str, Dict[str, Location]] = dict()
        # dict of locations where a module could not be imported
        self.not_found: Dict[Location, str] = dict()
        # dict of modules to duplicate module imports and the location where they are imported
        self.duplicates: Dict[str, Dict[str, Location]] = dict()
        # dict of locations from where a module is imported that is already imported from another location
        self.reimports: Dict[Location, Dict[Location, str]] = dict()
        # dict of module and the cycle it belongs to
        self.cycles: Dict[str, List[str]] = dict()
        if not self.success:
            self.exceptions.extend(parser.exception)
        if self.success:
            def catcher(symbol_type_constructor):
                def wrapper(node):
                    try:
                        symbol = symbol_type_constructor(node)
                        return symbol
                    except Exception as e:
                        self.exceptions.append(e)
                return wrapper

            self.symis: List[SymiSymbol] = list(
                filter(None, map(catcher(SymiSymbol.from_node),
                                 parser.root.finditer(SymiSymbol.SYM_PATTERN))))

            self.gimports: List[GimportSymbol] = list(
                filter(None, map(catcher(GimportSymbol.from_node),
                                 parser.root.finditer(GimportSymbol.GIMPORT_PATTERN))))

            self.trefis: List[TrefiSymbol] = list(
                filter(None, map(catcher(TrefiSymbol.from_node),
                                 parser.root.finditer(TrefiSymbol.TREFI_PATTERN))))

            self.defis: List[DefiSymbol] = list(
                filter(None, map(catcher(DefiSymbol.from_node),
                                 parser.root.finditer(DefiSymbol.DEFI_PATTERN))))

            modules: List[ModuleDefinitonSymbol] = list(
                filter(None, map(catcher(ModuleDefinitonSymbol.from_node),
                                 parser.root.finditer(ModuleDefinitonSymbol.MODULE_PATTERN))))

            if len(modules) > 1:
                raise Exception(f'Multiple modules in file "{file}"')

            if len(modules) == 1:
                self.module, = modules

            bindings: List[ModuleBindingDefinitionSymbol] = list(
                filter(None, map(catcher(ModuleBindingDefinitionSymbol.from_node),
                                 parser.root.finditer(ModuleBindingDefinitionSymbol.MODULE_BINDING_PATTERN))))

            if len(bindings) > 1:
                raise Exception(f'Multiple bindings in file "{file}"')

            if len(bindings) == 1:
                self.binding, = bindings

            if self.binding and self.module:
                raise LinterException(f'In file "{file}":'
                                      f' Files may not include a module and a binding at the same time')


class Linter(FileWatcher):
    def __init__(self):
        super().__init__(['.tex'])
        self._map_file_to_document: Dict[str, Document] = {}
        self._map_module_identifier_to_bindings: Dict[str, Document] = {}
        self._map_module_identifier_to_module: Dict[str, Document] = {}
        self._watched_directories: List[str] = []
        self.failed_to_parse: Dict[str, List[Exception]] = {}

        self.exceptions = {}

    def module_at_position(self, file, line, column):
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
        added = 0
        for d in glob(directory, recursive=True):
            if os.path.isdir(d):
                if d not in self._watched_directories:
                    self._watched_directories.append(d)
                    added += 1
        return added

    def update(self, n_jobs=None, debug=False):
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
                self._unlink(file)
            except Exception as e:
                self.exceptions.setdefault(file, [])
                self.exceptions[file].append(e)

        # Parse all files in parallel or sequential
        with multiprocessing.Pool(n_jobs) as pool:
            documents = pool.map(Document, modified)

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

        return len(documents)

    def print_outline(self, modules=None):
        from termcolor import colored
        for modid, module in self._map_module_identifier_to_module.items():
            if modules and modid not in modules:
                continue
            print(colored('MODULE', 'yellow'), colored(modid, 'green'), module.document.file)
            print(colored('\tIMPORTS', 'blue'))
            for gimport in module.gimports:
                print('\t\t', colored(gimport.imported_module, 'green'))
            print(colored('\tSYMBOLS', 'magenta'))
            for sym in module.symis:
                print('\t\t', colored(sym.name, 'grey'), sym.symbol)
            for lang, binding in self._map_module_identifier_to_bindings.get(modid, {}).items():
                print(colored("\tBINDING", 'green'), colored(lang, 'grey'), binding.document.file)
                for defi in binding.defis:
                    print(colored("\t\tDEFI", 'red'), colored(defi.name, 'grey'), defi.symbol)
                for trefi in binding.trefis:
                    print(colored("\t\tTREFI", 'blue'), colored(trefi.target_module, 'green'), colored(trefi.target_symbol_name, 'grey'), trefi.symbol)

    def _unlink(self, file: str):
        """ Deletes all symbols/links provided by the file if tracked. """
        if file in self.exceptions:
            del self.exceptions[file]
        if file in self.failed_to_parse:
            del self.failed_to_parse[file]
        doc = self._map_file_to_document.get(file)
        if doc is not None:
            module_id = str(doc.module_identifier)

            binding = self._map_module_identifier_to_bindings.get(module_id)
            if binding is not None:
                print('-BINDING', file)
                del binding[doc.binding.lang]
            else:
                module = self._map_module_identifier_to_module.get(module_id)
                if module == doc:
                    print('-MODULE', file)
                    del self._map_module_identifier_to_module[module_id]
                else:
                    raise Exception(f"Failed to clear file links at {file}")

    def _link(self, document: Document):
        """ Starts tracking a document. Indexes links and symbols provided by it. """
        self._map_file_to_document[document.file] = document
        module = str(document.module_identifier)
        if document.binding:
            print("+BINDING", module, document.binding.lang, os.path.basename(document.file))
            self._map_module_identifier_to_bindings.setdefault(module, {})
            if document.binding.lang in self._map_module_identifier_to_bindings[module]:
                raise Exception(f'Duplicate binding for language {document.binding.lang}'
                                f'in module {module} at {document.file}')
            self._map_module_identifier_to_bindings[module][document.binding.lang] = document

        if document.module:
            print("+MODULE", module, os.path.basename(document.file))
            if module in self._map_module_identifier_to_module:
                raise Exception(f'Duplicate module definition of module {module} at {document.file}')
            self._map_module_identifier_to_module[module] = document
            self._
