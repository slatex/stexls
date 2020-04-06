from __future__ import annotations
from typing import Dict, Optional, Set, Union
import itertools, functools
from pathlib import Path
from collections import defaultdict
from stexls.util.location import *
from stexls.compiler.parse import *
from stexls.compiler.symbols import *
from stexls.compiler.exceptions import *

__all__ = ['StexObject']

class StexObject:
    def __init__(self):
        # Set of files used to compile this object
        self.files: Set[Path] = set()
        # Dependent module <str> from path hint <Path> referenced at a <Location> and an export flag <bool>
        self.dependencies: Dict[str, Dict[Path, Dict[Location, bool]]] = defaultdict(dict)
        # Symbol table with definitions: Key is symbol name for easy search access by symbol name
        self.symbol_table: Dict[str, List[Symbol]] = defaultdict(list)
        # Referenced symbol <str> in file <Path> at written in range <Range>
        self.references: Dict[Path, Dict[Range, str]] = defaultdict(dict)
        # Dict of list of errors generated at specific location
        self.errors: Dict[Location, List[Exception]] = defaultdict(list)

    def is_object_changed(self, other: StexObject) -> bool:
        """ Checks whether or not the two objects have the same set of dependencies and exported symbols.

        Parameters:
            other: Other stex object to compare to.

        Returns:
            True if the two objects have differences in the set of exported symbols or dependencies
            between them.
        """
        for id, paths in itertools.chain(self.dependencies.items(), other.dependencies.items()):
            for path in paths:
                if self.dependencies.get(id, {}).get(path) is None or other.dependencies.get(id, {}).get(path) is None:
                    return True
        for id in itertools.chain(self.symbol_table, other.symbol_table):
            if  self.symbol_table.get(id) is None or other.symbol_table.get(id) is None:
                return True
        return False

    def resolve(self, id: str, unique: bool = True, must_resolve: bool = True) -> List[Symbol]:
        """ Resolves an id.

        Parameters:
            id: Id to resolve.
            unique: IfOTrue, raisesoan exception if the resolved symbol has multiple definitions. bjects that have  ptional  Defaults to True.
            must_resolve: If true, raises an exception if no definition for the symbol was found.
        
        Returns:
            List of symbol definitions with the given id.
            LengthLof en 0 orif unique is True. 1  len 1 if unique=True,
            Length of >= 1 if must_resolve is True.
            Always length 1 if unique and must_resolve are both True.
        """
        symbols = self.symbol_table.get(id, [])
        if unique and len(symbols) > 1:
            raise CompilerError(f'Multiple symbols with id "{id}" found: {symbols}')
        if must_resolve and not symbols:
            raise CompilerError(f'Unable to resolve id "{id}".')
        return symbols

    def find_mhmodule_module(
        self,
        mhrepo: Optional[str],
        dir: Optional[str],
        path: Optional[str],
        context: str) -> List[str]:
        """ Search for modules that can be importet by the importmhmodule environment.

        Finds all fitting module names given a pattern like these:
        \\importmhmodule[mhrepo=<mhrepo>,dir=<dir>]{<context>
        \\importmhmodule[path=<path>]{<context>
        \\importmhmodule{<context>

        Parameters:
            mhrepo: Optional repository path hint: \\importmhmodule[mhrepo=<mhrepo>...
            dir: Optional mhrepo directory: \\importmhmodule[dir=<dir>...
            path: Optional path to the file: \\importmhmodule[]
            context: Substring of the module to find: \\importmhmodule{<context>
        
        Returns:
            List of names of modules that fit the given constraints and
            that are imported by this object.
        """
        pass
    
    def find_mhmodule_mhrepo(self, context: str) -> List[str]:
        """ Find paths to repositories that can be used as mhrepo= argument in importmhmodule environments.

        Parameters:
            context: Substring of the mhrepo to find: importmhrepo[mhrepo=<context>
        
        Returns:
            List of strings which can be used as a mhrepo argument and that fit the
            given context.
        """
        pass

    def find_mhmodule_dir(self, mhrepo: Optional[str], context: str) -> List[str]:
        """ Find directories with mhmodules in them, given an optional mhrepo prefix.

        Finds strings that can be used in dir= arguments of importmhmodule environments,
        given an optional mhrepo argument as context.

        Parameters:
            mhrepo: Optional mhrepo context: importmhrepo[mhrepo=<mhrepo>]
            context: Current dir argument prefix: importmhrepo[mhrepo=<mhrepo>,dir=<context>...
        
        Returns:
            List of strings which are valid dir= arguments given the mhrepo as context.
        """
        pass

    def find_mhmodule_path(self, mhrepo: Optional[str], context: str) -> List[str]:
        """ Find paths with mhmodules in them, given an optional mhrepo prefix

        Parameters:
            mhrepo: Optional mhrepo context: importmhmodule[mhrepo=<mhrepo>]
            context: Current path argument prefix: importmhmodule[mhrepo=<mhrepo>,path=<context>...]
        
        Returns:
            List of valid strings that can be used as path= arguments given the mhrepo as context.
        """
        pass
    
    def find_gimport_repo(self, context: str) -> List[str]:
        """ Finds paths to repositories which can be targets for a gimport.

        Parameters:
            context: Current argument context: gimport[<context>...
        
        Returns:
            List of strings that are valid gimport repository argument targets.
        """
        pass

    def find_gimport_module(self, repository: Optional[str], context: str) -> List[str]:
        """ Finds module names that can be targets for gimport environments.

        Parameters:
            repository: Optional target repository path: gimport[<repository>]{..}
            context: Current prefix of the module name: gimport{<context>...
        
        Returns:
            List of valid strings that can be used as the argument of a gimport.
        """
        pass

    def find_module_name(self, context: str) -> List[str]:
        """ Find module names with the current context as prefix.

        This can be used to find completions for modules where needed:
        trefi[<context>...
        
        This can NOT be used for gimports and importmhmodule as they
        have their own functions for searching modules given their respective
        other arguments, like repository paths in gimports and directories in importmhmodules.

        Parameters:
            context: Prefix of the module to search for.
        
        Returns:
            List of modules with the context as prefix.
        """
        pass

    def find_symbol_name(self, module: Optional[str], context: str) -> List[str]:
        """ Find symbol names with the context as prefix and optionally in the specified module.

        This function can be used to find completions for trefis and defis.
        For example:
        mtrefi[<module>?<context>...
        mtrefi[?<context>...
        defi[name=<context>...
        symdef[name=<context>...

        Parameters:
            module: Optional specific module name the symbol name must be found.
            context: Current prefix of the symbol name to find.
        
        Returns:
            List of symbol names with the given context.
        """
        pass

    def find_symbol_tokens(self, module: Optional[str], name: Optional[str], context: str) -> List[Tuple[str]]:
        """ Finds the tuples of text tokens of all symbol definitions given the context.

        This can be used to generate completions for environments which need multiple tokens.
        For eaxmple:
        mtrefiii[<module>?<name>]{<context>...
        mtrefii[?<name>]{<context>...
        trefiii[<module>]{<context>...
        defii{<context>...
        defii[name=<name>]{<context>

        Parameters:
            module: Optional module to search symbols in.
            name: Optional name of the symbol to find.
            context: Context to search for.
        
        Returns:
            The strings which are valid at their respective positions.
        """
        pass

    def link(self, other: StexObject, finalize: bool = False):
        self.files.update(other.files)
        if finalize:
            for location, errors in other.errors.items():
                self.errors[location].extend(errors)
            for module, infos in other.dependencies.items():
                for path, locations in infos.items():
                    if not path.is_file():
                        for location in locations:
                            self.errors[location].append(
                                LinkError(f'Unable to locate file: "{path}"'))
                    elif module not in self.symbol_table:
                        for location in locations:
                            self.errors[location].append(
                                LinkError(f'Missing module: "{path}" does not export module "{module}"'))
                    elif module in self.dependencies:
                        for previous_location, bool in self.dependencies[module].get(path, {}).items():
                            for location in locations:
                                self.errors[location].append(
                                    LinkWarning(f'Module "{module}" previously imported at "{previous_location.format_link()}"'))
        for module, paths in other.dependencies.items():
            for path, locations in paths.items():
                for location, public in locations.items():
                    # add dependencies only if public, except for the finalize case, then always add
                    if public or finalize:
                        self.dependencies[module].setdefault(path, {})[location] = public
        for id, symbols in other.symbol_table.items():
            if id in self.symbol_table:
                if finalize:
                    for symbol in symbols:
                        for previous in self.symbol_table[id]:
                            self.errors[symbol.location].append(
                                LinkError(
                                    f'Duplicate symbol definition: '
                                    f'"{id}" previously defined at "{previous.location.format_link()}"'))
            else:
                self.symbol_table[id].extend(symbols)
        if finalize:
            for path, ranges in other.references.items():
                for range, id in ranges.items():
                    location = Location(path, range)
                    if id not in self.symbol_table:
                        self.errors[location].append(
                            LinkError(f'Undefined Unreos: "{id}"'))
                self.references[path].update(ranges)

    def copy(self) -> StexObject:
        ' Creates a copy of all the storage containers. '
        o = StexObject()
        o.files = self.files.copy()
        for k1, d1 in self.dependencies.items():
            for k2, d2 in d1.items():
                o.dependencies[k1][k2] = d2.copy()
        for k1, l1 in self.symbol_table.items():
            o.symbol_table[k1] = l1.copy()
        for k1, d1 in self.references.items():
            o.references[k1] = d1.copy()
        for k1, l1 in self.errors.items():
            o.errors[k1] = l1.copy()
        return o

    @property
    def path(self) -> Optional[Path]:
        """ Returns the path of the file from which this object was contained.
            Returns None if the path is not unique, because multiple files are contained.
        """
        if len(self.files) != 1:
            return None
        return next(iter(self.files))

    @property
    def module(self) -> Optional[str]:
        ' Returns an identifier for the module this object contains, if it is the only one. Else returns None. '
        modules = [
            id
            for id, symbols in self.symbol_table.items()
            for symbol in symbols
            if symbol.identifier.symbol_type == SymbolType.MODULE
        ]
        if len(modules) > 1:
            return None
        return next(iter(modules), None)

    def format(self) -> str:
        ' Formats the contents of this object for a pretty print. '
        formatted = 'Contains files:'
        for f in self.files:
            formatted += '\n\t' + str(f)

        formatted += '\n\nDepends on:'
        if not self.dependencies:
            formatted += ' <no dependencies>'
        else:
            for module, files in self.dependencies.items():
                for filename, locations in files.items():
                    for location, public in locations.items():
                        for location in locations:
                            access = 'public' if public else 'private'
                            formatted += f'\n\t{location.format_link()}:{access} {module} from "{filename}"'
        
        formatted += '\n\nSymbols:'
        if not self.symbol_table:
            formatted += ' <no symbols>'
        else:
            for id, symbols in self.symbol_table.items():
                for symbol in symbols:
                    formatted += f'\n\t{symbol.location.format_link()}:{symbol.access_modifier.value} {symbol.qualified_identifier}'

        formatted += '\n\nReferences:'
        if not self.references:
            formatted += ' <no references>'
        else:
            for path, ranges in self.references.items():
                for range, id in ranges.items():
                    location = Location(path, range)
                    formatted += f'\n\t{location.format_link()}:{id}'
        
        formatted += '\n\nErrors:'
        if not self.errors:
            formatted += ' <no errors>'
        else:
            for location, errors in self.errors.items():
                for error in errors:
                    formatted += f'\n\t{location.format_link()}:{error}'
        
        return formatted
    
    def add_dependency(self, location: Location, file: Path, module_name: str, export: bool = False):
        """ Adds a dependency to a imported module in another file.

        Parameters:
            location: Location of where this dependency is created.
            file: Path to file that is referenced in the dependency.
            module_name: Module to import from that file.
            export: Export the imported symbols again.
        """
        self.dependencies[module_name].setdefault(file, dict())[location] = export

    def add_reference(self, location: Location, referenced_id: str):
        """ Adds a reference.

        Parameters:
            location: Location of the string that creates this reference
            referenced_id: The id of the referenced symbol.
        """
        self.references[location.uri][location.range] = referenced_id

    def add_symbol(self, symbol: Symbol, export: bool = False, duplicate_allowed: bool = False):
        symbol.access_modifier = AccessModifier.PUBLIC if export else AccessModifier.PRIVATE
        if not duplicate_allowed:
            for duplicate in self.symbol_table.get(symbol.qualified_identifier.identifier, ()):
                raise CompilerError(
                    f'Duplicate symbol definition of {symbol.qualified_identifier}'
                    f' previously defined at "{duplicate.location.format_link()}"')
        self.symbol_table[symbol.qualified_identifier.identifier].append(symbol)

    @staticmethod
    def compile(parsed: ParsedFile) -> Optional[StexObject]:
        def _create(errors):
            obj = StexObject()
            obj.files.add(parsed.path)
            if errors:
                obj.errors = errors.copy()
            return obj
        number_of_roots = len(parsed.modnls) + len(parsed.modsigs) + int(len(parsed.modules) > 0)
        if number_of_roots > 1:
            obj = _create(parsed.errors)
            for env in itertools.chain(parsed.modnls, parsed.modsigs, parsed.modules):
                obj.errors[env.location].append(
                    CompilerError(f'Too many types of roots found: Found {number_of_roots}, expected up to 1'))
            if obj.errors or obj.references or obj.symbol_table:
                yield obj
        else: 
            toplevels = list(parsed)
            if toplevels:
                for toplevel in toplevels:
                    for modsig in toplevel.modsigs:
                        obj = _create(toplevel.errors)
                        _compile_modsig(modsig, obj, toplevel)
                        yield obj
                    for modnl in toplevel.modnls:
                        obj = _create(toplevel.errors)
                        _compile_modnl(modnl, obj, toplevel)
                        yield obj
                    for module in toplevel.modules:
                        obj = _create(toplevel.errors)
                        _compile_module(module, obj, toplevel)
                        yield obj
            else:
                obj = _create(parsed.errors)
                _compile_free(obj, parsed)
                if obj.errors or obj.references or obj.symbol_table:
                    yield obj


def _map_compile(compile_fun, arr: List, obj: StexObject):
    for item in arr:
        try:
            compile_fun(item, obj)
        except CompilerError as e:
            obj.errors[item.location].append(e)

def _compile_free(obj: StexObject, parsed_file: ParsedFile):
    _report_invalid_environments('file', parsed_file.modnls, obj)
    _report_invalid_environments('file', parsed_file.modules, obj)
    _report_invalid_environments('file', parsed_file.defis, obj)
    _report_invalid_environments('file', parsed_file.symdefs, obj)
    _report_invalid_environments('file', parsed_file.syms, obj)
    _report_invalid_environments('file', parsed_file.gimports, obj)
    _map_compile(_compile_importmodule, parsed_file.importmodules, obj)
    _map_compile(functools.partial(_compile_trefi, None), parsed_file.trefis, obj)

def _compile_modsig(modsig: Modsig, obj: StexObject, parsed_file: ParsedFile):
    for invalid_environment in itertools.chain(
        parsed_file.modnls,
        parsed_file.modules,
        parsed_file.defis,
        parsed_file.trefis):
        obj.errors[invalid_environment.location].append(CompilerWarning(f'Invalid environment of type {type(invalid_environment).__name__} in mhmodnl.'))
    name_location = modsig.location.replace(positionOrRange=modsig.name.range)
    module = ModuleSymbol(name_location, modsig.name.text, full_range=modsig.location, module_type=ModuleType.MODSIG)
    if parsed_file.path.name != f'{modsig.name.text}.tex':
        obj.errors[name_location].append(CompilerWarning(f'Invalid modsig filename: Expected "{modsig.name.text}.tex"'))
    obj.add_symbol(module, export=True)
    _map_compile(_compile_gimport, parsed_file.gimports, obj)
    _map_compile(_compile_importmodule, parsed_file.importmodules, obj)
    _map_compile(functools.partial(_compile_sym, module), parsed_file.syms, obj)
    _map_compile(functools.partial(_compile_symdef, module), parsed_file.symdefs, obj)

def _compile_gimport(gimport: GImport, obj: StexObject):
    obj.add_dependency(gimport.location, gimport.path_to_imported_file, gimport.module.text.strip(), export=gimport.export)
    obj.add_reference(gimport.location, gimport.module.text)

def _compile_importmodule(importmodule: ImportModule, obj: StexObject):
    obj.add_dependency(importmodule.location, importmodule.path_to_imported_file, importmodule.module.text.strip(), export=importmodule.export)
    obj.add_reference(importmodule.location, importmodule.module.text)

def _compile_sym(module: ModuleSymbol, sym: Symi, obj: StexObject):
    symbol = DefSymbol(
        location=sym.location,
        name=sym.name,
        module=module.qualified_identifier,
        noverb=sym.noverb.is_all,
        noverbs=sym.noverb.langs)
    obj.add_symbol(symbol, export=True)

def _compile_symdef(module: ModuleSymbol, symdef: Symdef, obj: StexObject):
    symbol = DefSymbol(
        location=symdef.location,
        name=symdef.name.text,
        module=module.qualified_identifier,
        noverb=symdef.noverb.is_all,
        noverbs=symdef.noverb.langs)
    obj.add_symbol(symbol, duplicate_allowed=True, export=True)

def _compile_modnl(modnl: Modnl, obj: StexObject, parsed_file: ParsedFile):
    if parsed_file.path.name != f'{modnl.name.text}.{modnl.lang.text}.tex':
        obj.errors[modnl.location].append(CompilerWarning(f'Invalid modnl filename: Expected "{modnl.name.text}.{modnl.lang.text}.tex"'))
    for invalid_environment in itertools.chain(
        parsed_file.modsigs,
        parsed_file.modules,
        parsed_file.importmodules,
        parsed_file.symdefs,
        parsed_file.syms):
        obj.errors[invalid_environment.location].append(CompilerWarning(f'Invalid environment of type {type(invalid_environment).__name__} in modnl.'))
    module_id = SymbolIdentifier(modnl.name.text, SymbolType.MODULE)
    name_location = modnl.location.replace(positionOrRange=modnl.name.range)
    obj.add_reference(name_location, module_id.identifier)
    obj.add_dependency(name_location, modnl.path, modnl.name.text)
    _map_compile(_compile_gimport, parsed_file.gimports, obj)
    _map_compile(functools.partial(_compile_defi, module_id), parsed_file.defis, obj)
    _map_compile(functools.partial(_compile_trefi, module_id), parsed_file.trefis, obj)

def _compile_defi(module: SymbolIdentifier, defi: Defi, obj: StexObject, create: bool = False):
    if create:
        symbol = DefSymbol(defi.location, defi.name, module)
        obj.add_symbol(symbol, export=True)
    else:
        defi_id = SymbolIdentifier(defi.name, SymbolType.SYMBOL)
        symbol_id = module.append(defi_id)
        obj.add_reference(defi.location, symbol_id.identifier)

def _compile_trefi(module_id: SymbolIdentifier, trefi: Trefi, obj: StexObject):
    if trefi.module:
        module_id = SymbolIdentifier(trefi.module.text, SymbolType.MODULE)
        reference_location = trefi.location.replace(positionOrRange=trefi.module.range)
        obj.add_reference(reference_location, module_id.identifier)
    elif module_id is None:
        raise CompilerError('Invalid trefi configuration: Missing parent module name')
    target_symbol_id = module_id.append(SymbolIdentifier(trefi.name, SymbolType.SYMBOL))
    obj.add_reference(trefi.location, target_symbol_id.identifier)

def _compile_module(module: Module, obj: StexObject, parsed_file: ParsedFile):
    _report_invalid_environments('module', itertools.chain(parsed_file.modsigs, parsed_file.modnls, parsed_file.syms), obj)
    if module.id:
        name_location = module.location.replace(positionOrRange=module.id.range)
        module = ModuleSymbol(name_location, module.id.text, full_range=module.location, module_type=ModuleType.MODULE)
        obj.add_symbol(module, export=True)
        _map_compile(_compile_importmodule, parsed_file.importmodules, obj)
        _map_compile(_compile_gimport, parsed_file.gimports, obj)
        _map_compile(functools.partial(_compile_symdef, module), parsed_file.symdefs, obj)
        _map_compile(functools.partial(_compile_defi, module.qualified_identifier, create=True), parsed_file.defis, obj)
        _map_compile(functools.partial(_compile_trefi, module.qualified_identifier), parsed_file.trefis, obj)
    else:
        _report_invalid_environments('module', itertools.chain(parsed_file.symdefs, parsed_file.defis), obj)
        _map_compile(_compile_importmodule, parsed_file.importmodules, obj)
        _map_compile(_compile_gimport, parsed_file.gimports, obj)
        _map_compile(functools.partial(_compile_trefi, None), parsed_file.trefis, obj)

def _report_invalid_environments(env_name: str, lst: List[ParsedEnvironment], obj: StexObject):
    for invalid_environment in lst:
        obj.errors[invalid_environment.location].append(
            CompilerWarning(f'Invalid environment of type {type(invalid_environment).__name__} in {env_name}.'))
