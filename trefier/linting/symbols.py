from __future__ import annotations
from typing import Tuple, List, Union, Optional
import re

from ..misc.location import *
from ..parser.latex_parser import Environment, Node

from .exceptions import *
from .identifiers import *

__all__ = ['Symbol',
           'ModuleDefinitonSymbol',
           'ModuleBindingDefinitionSymbol',
           'SymiSymbol',
           'GimportSymbol',
           'TrefiSymbol',
           'DefiSymbol']

def _node_to_location(node: Node) -> Location:
    """ Helper that transforms a node to a location.Location object """
    return Location(node.parser.file, Range(Position(*node.begin_position), Position(*node.end_position)))


def _linter_range_to_Range(linter_range: Tuple[Tuple[int, int], Tuple[int, int]]) -> Range:
    """ Helper that transforms the linter range tuple into a location.Range object """
    return Range(Position(*linter_range[0]), Position(*linter_range[1]))


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
        self.module_name = module_name
        self.module_and_file_name_mismatch = module_name != self.module.module_name

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
        self.bound_module_name = bound_module_name
        self.module_and_file_name_mismatch = bound_module_name != self.module.module_name
        self.module_lang_and_file_name_lang_mismatch = f'.{lang}.' not in file

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

    def __init__(self,
                 imported_module_location: Location,
                 imported_module: ModuleIdentifier,
                 repository_range: Optional[Range],
                 file: str,
                 full_range: Range):
        """ Gimport symbol \\gimport[imported_module.base/imported_module.repository]{imported_module.module_name} """
        super().__init__(file, full_range)
        self.imported_module_location = imported_module_location
        self.imported_module = imported_module
        self.repository_range = repository_range

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
            oarg_effective_range = oarg.effective_range
            oarg_begin = Position(oarg_effective_range[0][0], oarg_effective_range[0][1])
            oarg_end = Position(oarg_effective_range[1][0], oarg_effective_range[1][1])
            return GimportSymbol(
                Location(location.file, imported_module_arg_range),
                ModuleIdentifier(*parts, imported_module_name),
                Range(oarg_begin, oarg_end),
                gimport.parser.file,
                location.range
            )

        containing_module = containing_module or ModuleIdentifier.from_file(gimport.parser.file)
        return GimportSymbol(
            Location(location.file, imported_module_arg_range),
            ModuleIdentifier(containing_module.base, containing_module.repository_name, imported_module_name),
            None,
            gimport.parser.file,
            location.range
        )


class EnvironmentSymbolWithStaticArgumentCount(Symbol):
    MASTER_PATTERN = re.compile(r'([ma]*)(sym|tref|def)(i+)s?\*?|symdef')

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
        if env_name == 'symdef':
            self.is_alt = False
        else:
            self.is_alt = 'a' in match.group(1)

    def name_contains(self, position: Position) -> bool:
        """ Tests whether position is on top of any symbol name identifier """
        for location in self.symbol_name_locations:
            if location.range.contains(position):
                return True
        return False

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

        if match is None:
            raise LinterInternalException(f'{location} Invalid environment: {env.env_name}')

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

    @staticmethod
    def get_name_argument_and_location(env: Environment) -> Optional[Tuple[str, Location]]:
        if len(env.oargs) < 1:
            return None
        oarg = env.oargs[0]
        pattern = re.compile(r'([\[,]\s*name\s*=\s*)(.+?)(?:[$\s,\]]|$)')
        matches = list(re.finditer(pattern, oarg.text))
        if len(matches) != 1:
            return None
        match = matches[0]
        symbol_name = match.group(2)
        oarg_begin, oarg_end = list(oarg.split_range(pattern, keep_delimeter=True))[1]
        oarg_begin += len(match.group(1))
        oarg_end = oarg_begin + len(symbol_name)
        return symbol_name, Location(env.parser.file, Range(
            Position(*env.parser.offset_to_position(oarg_begin)),
            Position(*env.parser.offset_to_position(oarg_end))
        ))


class SymiSymbol(EnvironmentSymbolWithStaticArgumentCount):
    SYM_PATTERN = re.compile(r'symi+s?\*?|symdef')

    def __init__(self,
                 symbol_name: str,
                 symbol_name_locations: List[Location],
                 search_terms: List[List[str]],
                 env_name: str,
                 file: str,
                 full_range: Range):
        super().__init__(symbol_name, symbol_name_locations, search_terms, env_name, file, full_range)

    @staticmethod
    def from_node(symbol: Environment):
        if symbol.env_name == 'symdef':
            location = _node_to_location(symbol)
            name_argument = EnvironmentSymbolWithStaticArgumentCount.get_name_argument_and_location(symbol)
            if name_argument is not None:
                # first use name= argument as symbol name
                symbol_name, symbol_name_location = name_argument
                symbol_name_locations = [symbol_name_location]
            elif len(symbol.rargs) >= 1:
                # else use first rarg
                symbol_name_location = None
                rarg = symbol.rargs[0].remove_brackets()
                symbol_name_locations = [_node_to_location(rarg)]
                symbol_name = rarg.text.strip()
            else:
                # else exception
                raise LinterInternalException.create(location, f'Expected "name=" argument in symdef')
            return SymiSymbol(
                symbol_name, symbol_name_locations,
                [], 'symdef', symbol.parser.file, location.range
            )
        else:
            symbol_name, symbol_name_locations, search_terms = EnvironmentSymbolWithStaticArgumentCount.get_info(symbol)

            location = _node_to_location(symbol)

            return SymiSymbol(
                symbol_name, symbol_name_locations, search_terms,
                symbol.env_name, symbol.parser.file, location.range)


class DefiSymbol(EnvironmentSymbolWithStaticArgumentCount):
    DEFI_PATTERN = re.compile(r'[ma]*defi+s?\*?')

    def __init__(self,
                 name_argument_location: Location,
                 symbol_name: str,
                 symbol_name_locations: List[Location],
                 search_terms: List[List[str]],
                 env_name: str,
                 file: str,
                 full_range: Range):
        super().__init__(symbol_name, symbol_name_locations, search_terms, env_name, file, full_range)
        self.name_argument_location = name_argument_location

    @staticmethod
    def from_node(defi: Environment) -> DefiSymbol:
        symbol_name, symbol_name_locations, search_terms = EnvironmentSymbolWithStaticArgumentCount.get_info(defi)

        location = _node_to_location(defi)

        name_argument_location = None
        name_argument = EnvironmentSymbolWithStaticArgumentCount.get_name_argument_and_location(defi)
        if name_argument is not None:
            symbol_name, name_argument_location = name_argument
            symbol_name_locations.insert(0, name_argument_location)

        return DefiSymbol(
            name_argument_location, symbol_name, symbol_name_locations, search_terms,
            defi.env_name, defi.parser.file, location.range)


class TrefiSymbol(EnvironmentSymbolWithStaticArgumentCount):
    TREFI_PATTERN = re.compile(r'[ma]*trefi+s?\*?')

    def __init__(
        self,
        target_module: Optional[str],
        target_module_location: Optional[Location],
        target_symbol_location: Optional[Location],
        symbol_name: str,
        symbol_name_locations: List[Location],
        search_terms: List[List[str]],
        env_name: str,
        file: str,
        full_range: Range):
        super().__init__(symbol_name, symbol_name_locations, search_terms, env_name, file, full_range)
        assert target_module is None or isinstance(target_module, str)
        self.target_module = target_module
        self.target_module_location = target_module_location
        self.target_symbol_location = target_symbol_location

    @staticmethod
    def from_node(trefi: Environment) -> TrefiSymbol:
        symbol_name, symbol_name_locations, search_terms = EnvironmentSymbolWithStaticArgumentCount.get_info(trefi)

        location = _node_to_location(trefi)

        target_module_identifier: Optional[str] = None
        target_module_location: Optional[Location] = None
        target_symbol_location: Optional[Location] = None

        # get the module and optionally the symbol from an oarg if present
        if len(trefi.oargs) == 1:
            # get the token inside the oarg
            oarg = trefi.oargs[0].remove_brackets()

            # split on ?
            parts: List[Tuple[Tuple[int, int], Tuple[int, int], str]] = list(
                oarg.split_range(r'\?', as_position=True, return_lexemes=True))

            # must have at most 2 parts "a?b"
            # the last part must be defined. "?b" is allowed but "?" or "a?" is not.
            if len(parts) > 2 or not parts or not parts[-1] or not parts[-1][-1]:
                raise LinterException(
                    f'{location} Expected a trefi argument of the format'
                    f' "[<module>]", "[<module>?<name>]" or "[?<name>]", but found "[{oarg.text}]"')

            # assign new module from oarg or inherit in case of "trefi[?name]"
            if len(parts) >= 1 and parts[0][-1]:
                target_module_identifier = parts[0][-1]
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

        return TrefiSymbol(target_module_identifier, target_module_location, target_symbol_location,
                           symbol_name, symbol_name_locations, search_terms,
                           trefi.env_name, trefi.parser.file, location.range)
