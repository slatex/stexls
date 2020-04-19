from __future__ import annotations
from typing import Dict, Optional, Set, Union, Iterable, Callable, List, Tuple
from pathlib import Path
from collections import defaultdict
from hashlib import sha1
import multiprocessing
import pickle
import difflib
import itertools
import functools
import glob

from stexls.util.vscode import DocumentUri, Position, Range, Location

from .parser import *
from .symbols import *
from .exceptions import *

__all__ = ['Compiler', 'StexObject']

class StexObject:
    def __init__(self, root: Path):
        # Root directory of resolution
        self.root = root
        # Set of files used to compile this object
        self.files: Set[Path] = set()
        # Dependent module <str> from path hint <Path> referenced at a <Location> and an export flag <bool>
        self.dependencies: Dict[SymbolIdentifier, Dict[Path, Dict[Location, Tuple[bool, DefinitionType]]]] = defaultdict(dict)
        # Symbol table with definitions: Key is symbol name for easy search access by symbol name
        self.symbol_table: Dict[SymbolIdentifier, List[Symbol]] = defaultdict(list)
        # Referenced symbol <SymbolIdentifier> in file <Path> in range <Range>
        self.references: Dict[Path, Dict[Range, SymbolIdentifier]] = defaultdict(dict)
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
            if self.symbol_table.get(id) is None or other.symbol_table.get(id) is None:
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
        symbols = set(self.symbol_table.get(SymbolIdentifier(id, SymbolType.SYMBOL), ())) | set(self.symbol_table.get(SymbolIdentifier, SymbolType.MODULE), ())
        if unique and len(symbols) > 1:
            str_locations = '", "'.join(symbol.location.format_link() for symbol in symbols)
            raise CompilerError(f'Multiple symbols with id "{id}" found: {str_locations}')
        if must_resolve and not symbols:
            raise CompilerError(f'Unable to resolve id "{id}".')
        return symbols

    def find_mhmodule_module(
        self,
        current_file: Path,
        context: str,
        mhrepo: Optional[str] = None,
        path: Optional[str] = None,
        dir: Optional[str] = None) -> List[str]:
        """ Search for modules that can be importet by the importmhmodule environment.

        Finds all fitting module names given a pattern like these:
        importmhmodule[mhrepo=<mhrepo>,dir=<dir>]{<context>
        importmhmodule[path=<path>]{<context>
        importmhmodule{<context>

        Parameters:
            mhrepo: Optional repository path hint: importmhmodule[mhrepo=<mhrepo>...
            path: Optional path to the file: importmhmodule[path=<path>...
            dir: Optional mhrepo directory: importmhmodule[dir=<dir>...
            context: Substring of the module to find: importmhmodule{<context>
        
        Returns:
            List of names of modules that fit the given constraints and
            that are imported by this object.
        """
        path = ImportModule.build_path_to_imported_module(
            self.root,
            current_file,
            mhrepo,
            path,
            dir,
            None,
            context).expanduser().resolve().as_posix()
        return [
            symbol.identifier
            for id, symbols in self.symbol_table.items()
            for symbol in symbols
            if symbol.location.path.startswith(path)
            if str(symbol.identifier).startswith(context)
        ]
    
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

    @staticmethod
    def link_list(others: List[StexObject], root: Path) -> StexObject:
        ' Links new object with a list of other object, where the last object will be the finalized one. '
        link = StexObject(root)
        for other in others:
            link.link(other, finalize=other==others[-1])
        return link

    def link(self, other: StexObject, finalize: bool = False):
        self.files.update(other.files)
        if finalize:
            for location, errors in other.errors.items():
                self.errors[location].extend(errors)
            for module, paths in other.dependencies.items():
                for path, locations in paths.items():
                    if not path.is_file():
                        for location in locations:
                            self.errors[location].append(
                                LinkError(f'File targeted by import does not exist: "{path}"'))
                    if module not in self.symbol_table:
                        modules_set = set(
                            id.identifier
                            for id, symbols in self.symbol_table.items()
                            for symbol in symbols
                            if symbol.location.uri == path
                            and symbol.identifier.symbol_type == SymbolType.MODULE)
                        available_modules = '", "'.join(modules_set)
                        close_matches = difflib.get_close_matches(module.identifier, modules_set)
                        if close_matches:
                            close_matches = '", "'.join(close_matches)
                        for location in locations:
                            if close_matches:
                                self.errors[location].append(
                                    LinkError(f'Not a module: "{module.identifier}", did you maybe mean "{available_modules}"?'))
                            elif modules_set:
                                self.errors[location].append(
                                    LinkError(f'Not a module: "{module.identifier}", available modules are "{available_modules}"'))
                            else:
                                self.errors[location].append(
                                    LinkError(f'Not a module: "{module.identifier}"'))
                    if module in self.dependencies:
                        for previous_location, (_, module_type_hint) in self.dependencies[module].get(path, {}).items():
                            for location in locations:
                                self.errors[location].append(
                                    LinkWarning(f'Module "{module.identifier}" was indirectly imported at "{previous_location.format_link()}" and may be removed.'))
        for module, paths in other.dependencies.items():
            for path, locations in paths.items():
                for location, (public, module_type_hint) in locations.items():
                    # add dependencies only if public, except for the finalize case, then always add
                    if public or finalize:
                        self.dependencies[module].setdefault(path, {})[location] = (public, module_type_hint)
        for id, symbols in other.symbol_table.items():
            for symbol in symbols:
                self.add_symbol(symbol, export=None, severity=LinkError if finalize else None)
        if finalize:
            for path, ranges in other.references.items():
                for range, id in ranges.items():
                    location = Location(path, range)
                    if id not in self.symbol_table:
                        identifiers_of_same_type = (
                            symbol.qualified_identifier.identifier
                            for symbols in self.symbol_table.values()
                            for symbol in symbols
                            if symbol.identifier.symbol_type == id.symbol_type)
                        close_matches = set(difflib.get_close_matches(id.identifier, identifiers_of_same_type))
                        if close_matches:
                            close_matches_str = '", "'.join(close_matches)
                            self.errors[location].append(
                                LinkError(f'Undefined {id.symbol_type.value}: "{id.identifier}", did you maybe mean "{close_matches_str}"?'))
                        else:
                            self.errors[location].append(
                                LinkError(f'Undefined {id.symbol_type.value}: "{id.identifier}"'))
                self.references[path].update(ranges)

    def copy(self) -> StexObject:
        ' Creates a copy of all the storage containers. '
        object = StexObject(self.root)
        object.files = self.files.copy()
        for module, paths in self.dependencies.items():
            for path, locations in paths.items():
                object.dependencies[module][path] = locations.copy()
        for id, symbols in self.symbol_table.items():
            object.symbol_table[id] = symbols.copy()
        for path, references in self.references.items():
            object.references[path] = references.copy()
        for location, errors in self.errors.items():
            object.errors[location] = errors.copy()
        return object

    @property
    def path(self) -> Optional[Path]:
        """ Returns the path of the file from which this object was contained.
            Returns None if the path is not unique, because multiple files are contained.
        """
        if len(self.files) != 1:
            return None
        return next(iter(self.files))

    @property
    def module(self) -> Optional[SymbolIdentifier]:
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
                    for location, (public, module_type) in locations.items():
                        for location in locations:
                            access = 'public' if public else 'private'
                            formatted += f'\n\t{location.format_link()}:{access} {module_type.name} {module} from "{filename}"'
        
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
    
    def add_dependency(
        self,
        location: Location,
        file: Path,
        module_name: str,
        module_type_hint: DefinitionType,
        export: bool = False):
        """ Adds a dependency to a imported module in another file.

        Parameters:
            location: Location of where this dependency is created.
            file: Path to file that is referenced in the dependency.
            module_name: Module to import from that file.
            module_type_hint: Hint for the expected type of the dependency.
            export: Export the imported symbols again.
        """
        self.dependencies[SymbolIdentifier(module_name, SymbolType.MODULE)].setdefault(file, dict())[location] = (export, module_type_hint)

    def add_reference(self, location: Location, referenced_id: SymbolIdentifier):
        """ Adds a reference.

        Parameters:
            location: Location of the string that creates this reference
            referenced_id: The id of the referenced symbol.
        """
        self.references[location.uri][location.range] = referenced_id

    def add_symbol(self, symbol: Symbol, export: Optional[bool] = False, severity: Optional[type] = CompilerError):
        if export is not None:
            symbol.access_modifier = AccessModifier.PUBLIC if export else AccessModifier.PRIVATE


        if severity is not None:
            previous_definitions = self.symbol_table.get(symbol.qualified_identifier, ())

            # Report errors from this file only if this file does not already contain a symdef
            if symbol.definition_type != DefinitionType.SYMDEF:
                this_file_contains_symdef_for_id = any(
                    symbol2.definition_type == DefinitionType.SYMDEF
                    for symbol2 in previous_definitions
                    if symbol2.location.uri == symbol.location.uri)
                if not this_file_contains_symdef_for_id:
                    for duplicate in previous_definitions:
                        self.errors[symbol.location].append(severity(
                            f'Duplicate symbol definition "{symbol.qualified_identifier}": '
                            f' Previously defined at "{duplicate.location.format_link()}"'))

            # Report errors for all definitions accross multiple files.
            definitions_in_other_files = (
                symbol2
                for symbol2 in previous_definitions
                if symbol2.location.uri != symbol.location.uri)
            for definition_in_other_file in definitions_in_other_files:
                self.errors[symbol.location].append(severity(
                    f'Duplicate symbol definition "{symbol.qualified_identifier}" from different files:'
                    f' Previously defined at "{definition_in_other_file.location.format_link()}"'))
        
        # finally also add the new symbol
        self.symbol_table[symbol.qualified_identifier].append(symbol)

    @staticmethod
    def compile(root: Path, parsed: ParsedFile) -> Iterable[StexObject]:
        def _create(errors):
            obj = StexObject(root)
            obj.files.add(parsed.path)
            if errors:
                obj.errors = errors.copy()
            return obj
        objects = []
        number_of_roots = len(parsed.modnls) + len(parsed.modsigs) + int(len(parsed.modules) > 0)
        if number_of_roots > 1:
            obj = _create(parsed.errors)
            for env in itertools.chain(parsed.modnls, parsed.modsigs, parsed.modules):
                obj.errors[env.location].append(
                    CompilerError(f'Too many types of roots found: Found {number_of_roots}, expected up to 1'))
            if obj.errors or obj.references or obj.symbol_table:
                objects.append(obj)
        else: 
            for toplevel in parsed.toplevels:
                if not (toplevel.modsigs or toplevel.modnls or toplevel.modules):
                    obj = _create(toplevel.errors)
                    _compile_free(obj, toplevel)
                    if obj.errors or obj.references or obj.symbol_table:
                        objects.append(obj)
                    continue
                for modsig in toplevel.modsigs:
                    obj = _create(toplevel.errors)
                    _compile_modsig(modsig, obj, toplevel)
                    objects.append(obj)
                for modnl in toplevel.modnls:
                    obj = _create(toplevel.errors)
                    _compile_modnl(modnl, obj, toplevel)
                    objects.append(obj)
                for module in toplevel.modules:
                    obj = _create(toplevel.errors)
                    _compile_module(module, obj, toplevel)
                    objects.append(obj)
        return objects


class Compiler:
    def __init__(self, root: Path, outdir: Path):
        self.root = root.expanduser().resolve().absolute()
        self.outdir = outdir.expanduser().resolve().absolute()
        self.objects: Dict[Path, List[StexObject]] = {}
        self.modules: Dict[Path, Dict[SymbolIdentifier, StexObject]] = {}

    def modified(self, files: Iterable[Path]) -> List[Path]:
        ' Returns list of files that need to be compiled because the objectfile does not exist or is out-of-date. '
        objectfiles = map(functools.partial(Compiler._get_objectfile_path, self.outdir), files)
        return [
            file
            for file, objectfile in zip(files, objectfiles)
            if not objectfile.is_file()
            or objectfile.lstat().st_mtime < file.lstat().st_mtime
        ]

    def compile(
        self,
        files: Iterable[Path],
        progressfn: Callable[[Iterable], Iterable] = None,
        use_multiprocessing: bool = True) -> Dict[Path, List[StexObject]]:
        progressfn = progressfn or (lambda x: x)
        files = list(files)
        visited: Set[Path] = set()
        results = None
        with multiprocessing.Pool() as pool:
            mapfn = pool.map if use_multiprocessing else map
            while files:
                compiled_files = mapfn(
                    functools.partial(
                        Compiler._load_or_compile_single_file,
                        outdir=self.outdir,
                        root=self.root), progressfn(files))
                objects: Dict[Path, List[StexObject]] = dict(filter(lambda x: x[-1], zip(files, compiled_files)))
                if results is None:
                    results = objects
                modules: Dict[Path, Dict[SymbolIdentifier, StexObject]] = {
                    path: {
                        object.module: object
                        for object in objects2
                        if object.module
                    }
                    for path, objects2 in objects.items()
                    if any(object.module for object in objects2)
                }
                self.objects.update(objects)
                self.modules.update(modules)
                visited.update(files)
                files = set()
                for file in objects.values():
                    for object in file:
                        for dependencies in object.dependencies.values():
                            files.update(dependencies)
                files -= visited
        return results

    @property
    def objectfiles(self) -> Set[Path]:
        return set(map(Path, glob.glob((self.outdir / '**/*.stexobj').as_posix(), recursive=True)))

    def clean_objects_up(self, files: Iterable[Path]) -> Set[Path]:
        transform = functools.partial(Compiler._get_objectfile_path, self.outdir)
        deleted = self.objectfiles - set(map(transform, map(Path, files)))
        for objectfile in deleted:
            if objectfile.is_file():
                objectfile.unlink()
                if not list(objectfile.parent.iterdir()):
                    objectfile.parent.rmdir()
        return deleted

    @staticmethod
    def _load_or_compile_single_file(file: Path, outdir: Path, root: Path) -> List[StexObject]:
        if file.is_file():
            objectfile = Compiler._get_objectfile_path(outdir, file)
            objectdir = objectfile.parent
            for _ in range(2): # give it two attempts to figure out whats going on
                if not objectfile.is_file() or objectfile.lstat().st_mtime < file.lstat().st_mtime:
                    # if not already compiled or the compiled object is old, create a new object
                    objectdir.mkdir(parents=True, exist_ok=True)
                    parsed = ParsedFile(file).parse()
                    objects = list(StexObject.compile(root, parsed))
                    with open(objectfile, 'wb') as fd:
                        pickle.dump(objects, fd)
                    return objects
                try:
                    # else load from cached
                    with open(objectfile, 'rb') as fd:
                        return pickle.load(fd)
                except:
                    # if loading fails, attempt to delete the cachefile
                    if objectfile.is_file():
                        objectfile.unlink()
                    # because this is a for loop, try again after deleting it
        return []

    @staticmethod
    def _compute_object_origin_hash(path: Path) -> str:
        ' Computes an object has for the path to an objectfile. '
        return sha1(path.parent.as_posix().encode()).hexdigest()

    @staticmethod
    def _get_objectfile_path(outdir: Path, file: Path) -> Path:
        ' Returns the file where the objectfile should be cached. '
        return outdir / Compiler._compute_object_origin_hash(file) / (file.name + '.stexobj')


def _map_compile(compile_fun, arr: List, obj: StexObject):
    for item in arr:
        try:
            compile_fun(item, obj)
        except CompilerError as e:
            obj.errors[item.location].append(e)

def _compile_free(obj: StexObject, parsed_file: ParsedFile):
    _report_invalid_environments('file', parsed_file.modnls, obj)
    _report_invalid_environments('file', parsed_file.modules, obj)
    _report_invalid_environments('file', parsed_file.modsigs, obj)
    _report_invalid_environments('file', parsed_file.defis, obj)
    _report_invalid_environments('file', parsed_file.symdefs, obj)
    _report_invalid_environments('file', parsed_file.syms, obj)
    _map_compile(_compile_importmodule, parsed_file.importmodules, obj)
    _map_compile(_compile_gimport, parsed_file.gimports, obj)
    _map_compile(functools.partial(_compile_trefi, None), parsed_file.trefis, obj)

def _compile_modsig(modsig: Modsig, obj: StexObject, parsed_file: ParsedFile):
    _report_invalid_environments('modsig', parsed_file.modnls, obj)
    _report_invalid_environments('modsig', parsed_file.modules, obj)
    _report_invalid_environments('modsig', parsed_file.defis, obj)
    _report_invalid_environments('modsig', parsed_file.trefis, obj)
    name_location = modsig.location.replace(positionOrRange=modsig.name.range)
    if parsed_file.path.name != f'{modsig.name.text}.tex':
        obj.errors[name_location].append(CompilerWarning(f'Invalid modsig filename: Expected "{modsig.name.text}.tex"'))
    module = ModuleSymbol(
        location=name_location,
        name=modsig.name.text,
        full_range=modsig.location,
        definition_type=DefinitionType.MODSIG)
    obj.add_symbol(module, export=True)
    _map_compile(_compile_gimport, parsed_file.gimports, obj)
    _map_compile(_compile_importmodule, parsed_file.importmodules, obj)
    _map_compile(functools.partial(_compile_sym, module), parsed_file.syms, obj)
    _map_compile(functools.partial(_compile_symdef, module), parsed_file.symdefs, obj)

def _compile_gimport(gimport: GImport, obj: StexObject):
    module_name = gimport.module.text.strip()
    obj.add_dependency(
        location=gimport.location,
        file=gimport.path_to_imported_file(obj.root),
        module_name=module_name,
        module_type_hint=DefinitionType.MODSIG,
        export=gimport.export)
    obj.add_reference(gimport.location, SymbolIdentifier(module_name, SymbolType.MODULE))

def _compile_importmodule(importmodule: ImportModule, obj: StexObject):
    module_name = importmodule.module.text.strip()
    obj.add_dependency(
        location=importmodule.location,
        file=importmodule.path_to_imported_file(obj.root),
        module_name=module_name,
        module_type_hint=DefinitionType.MODULE,
        export=importmodule.export)
    obj.add_reference(importmodule.location, SymbolIdentifier(module_name, SymbolType.MODULE))

def _compile_sym(module: ModuleSymbol, sym: Symi, obj: StexObject):
    symbol = VerbSymbol(
        location=sym.location,
        name=sym.name,
        module=module.qualified_identifier,
        noverb=sym.noverb.is_all,
        noverbs=sym.noverb.langs,
        definition_type=DefinitionType.SYM)
    obj.add_symbol(symbol, export=True)

def _compile_symdef(module: ModuleSymbol, symdef: Symdef, obj: StexObject):
    symbol = VerbSymbol(
        location=symdef.location,
        name=symdef.name.text,
        module=module.qualified_identifier,
        noverb=symdef.noverb.is_all,
        noverbs=symdef.noverb.langs,
        definition_type=DefinitionType.SYMDEF)
    obj.add_symbol(symbol, export=True)

def _compile_modnl(modnl: Modnl, obj: StexObject, parsed_file: ParsedFile):
    _report_invalid_environments('modnl', parsed_file.modsigs, obj)
    _report_invalid_environments('modnl', parsed_file.modules, obj)
    _report_invalid_environments('modnl', parsed_file.importmodules, obj)
    _report_invalid_environments('modnl', parsed_file.symdefs, obj)
    _report_invalid_environments('modnl', parsed_file.syms, obj)
    if parsed_file.path.name != f'{modnl.name.text}.{modnl.lang.text}.tex':
        obj.errors[modnl.location].append(CompilerWarning(f'Invalid modnl filename: Expected "{modnl.name.text}.{modnl.lang.text}.tex"'))
    module_id = SymbolIdentifier(modnl.name.text, SymbolType.MODULE)
    name_location = modnl.location.replace(positionOrRange=modnl.name.range)
    obj.add_reference(name_location, module_id)
    obj.add_dependency(
        location=name_location,
        file=modnl.path,
        module_name=modnl.name.text,
        module_type_hint=DefinitionType.MODSIG,
        export=True)
    _map_compile(_compile_gimport, parsed_file.gimports, obj)
    _map_compile(functools.partial(_compile_defi, module_id), parsed_file.defis, obj)
    _map_compile(functools.partial(_compile_trefi, module_id), parsed_file.trefis, obj)

def _compile_defi(module: SymbolIdentifier, defi: Defi, obj: StexObject, create: bool = False):
    if create:
        symbol = VerbSymbol(
            location=defi.location,
            name=defi.name,
            module=module,
            noverb=None,
            noverbs=None,
            definition_type=DefinitionType.SYMDEF) # TODO: Special definition type required?
        obj.add_symbol(symbol, export=True)
    else:
        defi_id = SymbolIdentifier(defi.name, SymbolType.SYMBOL)
        symbol_id = module.append(defi_id)
        obj.add_reference(defi.location, symbol_id)

def _compile_trefi(module_id: SymbolIdentifier, trefi: Trefi, obj: StexObject):
    if trefi.defi:
        if module_id is None:
            raise CompilerError('Invalid drefi configuration: Missing parent module name')
        id = SymbolIdentifier(trefi.name, SymbolType.SYMBOL)
        symbol = Symbol(trefi.location, id, module_id, DefinitionType.DEFI) # TODO: DefinitionType.DREFI required?
        obj.add_symbol(symbol, export=True)
    if trefi.module:
        module_id = SymbolIdentifier(trefi.module.text, SymbolType.MODULE)
        reference_location = trefi.location.replace(positionOrRange=trefi.module.range)
        obj.add_reference(reference_location, module_id)
    elif module_id is None:
        raise CompilerError('Invalid trefi configuration: Missing parent module name')
    target_symbol_id = module_id.append(SymbolIdentifier(trefi.name, SymbolType.SYMBOL))
    obj.add_reference(trefi.location, target_symbol_id)

def _compile_module(module: Module, obj: StexObject, parsed_file: ParsedFile):
    _report_invalid_environments('module', itertools.chain(parsed_file.modsigs, parsed_file.modnls, parsed_file.syms), obj)
    if module.id:
        name_location = module.location.replace(positionOrRange=module.id.range)
        module = ModuleSymbol(
            location=name_location,
            name=module.id.text,
            full_range=module.location,
            definition_type=DefinitionType.MODULE)
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
