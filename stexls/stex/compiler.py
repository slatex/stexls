"""
This module contains the compiler for stexls files with *.tex extensions.

The idea behind the compiler is that it mirrors a c++ compiler, which takes
c/c++ files and compiles them into *.o object files.
This compiler also creates object files with the *.stexobj extension.
They don't contain executable information like gcc objects, but symbol
names and locations. Also references to symbols and dependencies created
by import statements are recorded. Everything with location information, in order
to produce good error messages later.

Every object is only compiled with it's local information and dependencies are not
resolved here. In order to get global information the dependencies need to be linked
using the linker from the linker module and then the linter from the linter package.
"""
from __future__ import annotations

from numpy.lib.arraysetops import isin
from stexls.util.workspace import Workspace
from typing import Dict, Iterable, List, Tuple, Optional, Set
from pathlib import Path
from hashlib import sha1
import datetime
import difflib
import pickle
import functools
import logging
from time import time

log = logging.getLogger(__name__)

from stexls.vscode import Diagnostic, DiagnosticSeverity, Position, Range, Location
from stexls.util.format import format_enumeration
from stexls import trefier
from .references import Reference, ReferenceType
from .parser import *
from .symbols import *
from .exceptions import *
from . import util
from .diagnostics import Diagnostics

__all__ = ['Compiler', 'StexObject', 'Dependency', 'ObjectfileNotFoundError']


class ObjectfileNotFoundError(FileNotFoundError):
    pass


class ObjectfileIsCorruptedError(Exception):
    pass


class Dependency:
    def __init__(
        self,
        range: Range,
        scope: Symbol,
        module_name: str,
        module_type_hint: ModuleType,
        file_hint: Path,
        export: bool):
        """ Container for data required to resolve module dependencies / imports.

        Parameters:
            range: Range at which the dependency or import is generated.
            scope: The symbol table to which the imported symbols need to be added.
            module_name: The name of the module that is required.
            module_type_hint: The expected type of module signature. After resolving the module_name,
                the module_type of the resolved symbol should be the same as the dependency requires.
                The module type hint depends on for example the used import statement (gimport or usemodule)
            file_hint: Path to the file in which the dependent module is supposed to be defined inside or
                exported by.
            export: If True, this dependency should be exported, and visisible to modules that import this object.
                TODO: Check if "export" is a good term, because it's only set to false by 'usemodule'
        """
        self.range = range
        self.scope = scope
        self.module_name = module_name
        self.module_type_hint = module_type_hint
        self.file_hint = file_hint
        self.export = export

    def pretty_format(self, file: Path = None):
        ' A simple formatting method for debugging. '
        export = 'public' if self.export else 'private'
        if file:
            loc = f'{file}:{self.range.start.line}:{self.range.start.character}: '
        else:
            loc = ''
        return loc + f'{export} Import {self.module_type_hint.name} "{self.module_name}" from "{self.file_hint}"'

    def check_if_same_module_imported(self, other: Dependency):
        ' Returns true if two dependencies point to the same module. '
        if self.module_name == other.module_name:
            if self.scope == other.scope or self.scope.is_parent_of(other.scope):
                return True
        return False

    def __repr__(self):
        return f'[Dependency at={self.range} module={self.module_name} type={self.module_type_hint} file="{self.file_hint}" export={self.export}]'


class StexObject:
    """ Stex objects contain all the local information about dependencies, symbols and references in one file,
    as well as a list of errors that occured during parsing and compiling.
    """
    def __init__(self, file: Path):
        """ Initializes an object.

        Parameters:
            file: The file which was compiled.
        """
        # Path to source file from which this object is generated
        self.file = file
        # Root symbol tabel. All new symbols are added first to this.
        # TODO: Root location range should be the whole file.
        self.symbol_table: RootSymbol = RootSymbol(Location(file.as_uri(), Position(0, 0)))
        # List of dependencies this file has. There may exist multiple scopes with the same module/file as dependency.
        self.dependencies: List[Dependency] = list()
        # List of references. A reference consists of a range relative to the file that owns the reference and the symbol identifier that is referenced.
        self.references: List[Reference] = list()
        # Handler for diagnostics
        self.diagnostics: Diagnostics = Diagnostics()
        # Stores creation time
        self.creation_time = time()

    def get_definitions_at(self, position: Position) -> List[Location]:
        ' Queries symbol definitions at the given @position. '
        definitions = []
        # First step: Gather the symbol definitions which are directly positioned under the cursor
        for symbol in self.symbol_table.flat():
            # same file check
            if symbol.location.path != self.file:
                continue
            # ignore non-module and non-def symbols (e.g. scopes)
            if not isinstance(symbol, (ModuleSymbol, DefSymbol)):
                continue
            # Add the symbol if the symbol is positioned under cursor
            if symbol.location.range.contains(position):
                definitions.append(symbol.location)
        # Step 2: Resolve the references under the cursor
        # Buffer for the smallest reference under the cursor in case there are multiple references at the current position
        minimal_reference_range_buffer = None
        for ref in self.references:
            # check that the reference is positioned under cursor
            if ref.range.contains(position):
                # buffer the reference if nothing buffered yet
                if not minimal_reference_range_buffer:
                    minimal_reference_range_buffer = ref
                # if already one added: Select the smaller one
                elif ref.range.length < minimal_reference_range_buffer.range.length:
                    minimal_reference_range_buffer = ref
        if minimal_reference_range_buffer:
            # Get the definition the smallest reference points to
            definitions.extend(minimal_reference_range_buffer.resolved_locations)
        return definitions

    def is_source_modified(self, time_modified: float = None) -> bool:
        ''' Checks if the source was modified.

        Parameters:
            time_modified: An optional time_modified in case the file.lstat.st_mtime is overwritten by a buffered source.

        Returns:
            True if the source was modified after this object was created.
        '''
        if time_modified and time_modified > self.creation_time:
            return True
        return not self.file.is_file() or self.file.lstat().st_mtime > self.creation_time

    def check_if_any_related_file_is_newer_than_this_object(self, workspace: Workspace = None) -> bool:
        ''' Checks if any file given by self.related_files has a newer modified time than this object\'s creation time.

        Parameters:
            workspace: Workspace which is used to inspect time modified of a buffered file.

        Returns:
            True if the file is younger than the creation time.
        '''
        for file in set(self.related_files):
            if workspace and workspace.get_time_buffer_modified(file) > self.creation_time:
                return True
            elif file.is_file() and file.lstat().st_mtime > self.creation_time:
                return True
        return False

    @property
    def related_files(self) -> Iterable[Path]:
        ' Iterable of all files that are somehow referenced inside this object. '
        yield self.file
        for dep in self.dependencies:
            yield dep.file_hint
        for symbol in self.symbol_table.flat():
            yield symbol.location.path

    def find_similar_symbols(self, scope: Symbol, qualified: List[str], ref_type: ReferenceType) -> Dict[str, Set[Location]]:
        ''' Find simlar symbols with reference to a qualified name and an expected symbol type.

        Parameters:
            qualified: Qualified identifier of the input symbol.
            ref_type: Expected type of symbol the id should resolve into

        Returns:
            Dictionary map of symbol names as strings and the set of locations the symbol names are located at
        '''
        names: Dict[str, Set[Location]] = {}
        def f(symbol: Symbol):
            if ref_type.contains_any_of(symbol.reference_type):
                names.setdefault('?'.join(symbol.qualified), set()).add(symbol.location)
        self.symbol_table.traverse(lambda s: f(s))
        close_matches = difflib.get_close_matches('?'.join(qualified), names)
        return { match: names.get(match, set()) for match in close_matches }

    def format(self) -> str:
        ' Simple formatter for debugging, that prints out all information in this object. '
        f = f'\nFile: "{self.file}"'
        f += f'\nCreation time: {datetime.datetime.fromtimestamp(self.creation_time)}'
        f += '\nDependencies:'
        if self.dependencies:
            for dep in self.dependencies:
                loc = Location(self.file.as_uri(), dep.range).format_link()
                f += f'\n\t{loc}: {dep.module_name} from "{dep.file_hint}"'
        else:
            f += '\n\tNo dependencies.'
        f += '\nReferences:'
        if self.references:
            for ref in self.references:
                loc = Location(self.file.as_uri(), ref.range).format_link()
                f += f'\n\t{loc}: {"?".join(ref.name)} of type {ref.reference_type}'
        else:
            f += '\n\tNo references.'
        f += '\nDiagnostics:'
        if self.diagnostics:
            for diagnostic in self.diagnostics:
                f += f'\n\t{Location(self.file.as_uri(), diagnostic.range).format_link()} {diagnostic.severity.name} - {diagnostic.message} ({diagnostic.code})'
        else:
            f += '\n\tNo diagnostics.'
        f += '\nSymbol Table:'
        l = []
        def enter(l, s):
            l.append(f'{"  "*s.depth}├ {s}')
        self.symbol_table.traverse(lambda s: enter(l, s))
        f += '\n' + '\n'.join(l)
        return f

    def add_dependency(self, dep: Dependency):
        """ Registers a dependency that the owner file has to the in the dependency written file and module.

        Multiple dependencies from the same scope to the same module in the same file will be prevented from adding
        and import warnings will be generated.

        Parameters:
            dep: Information about the dependency.
        """
        for dep0 in self.dependencies:
            # TODO: this check probably means, that something was indirectly imported and can be ignored
            # TODO: this same error occurs in Symbol.import_from(): Fix both
            if dep0.check_if_same_module_imported(dep):
                # Skip adding this dependency
                previously_imported_at = Location(self.file.as_uri(), dep0.range)
                self.diagnostics.redundant_import_check(dep.range, dep.module_name, previously_imported_at)
                return
        self.dependencies.append(dep)

    def add_reference(self, reference: Reference):
        """ Registers a reference.

        Parameters:
            reference: Information about the reference.
        """
        self.references.append(reference)


class Compiler:
    """ This is the compiler class that mirrors a gcc command.

    The idea is that "c++ main.cpp -c -o outdir/main.o" is equal to "Compiler(cwd, outdir).compile(main.tex)"
    Important is the -c flag, as linking is seperate in our case.
    """
    def __init__(self, root: Path, outdir: Path):
        """ Creates a new compiler

        Parameters:
            root: Path to root directory.
            outdir: Directory into which compiled objects will be stored.
        """
        self.root_dir = root.expanduser().resolve().absolute()
        self.outdir = outdir.expanduser().resolve().absolute()
        self.model: trefier.models.Model = None

    def get_objectfile_path(self, file: Path) -> Path:
        ''' Gets the correct path the objectfile for the input file should be stored at.

        Parameters:
            file: Path to sourcefile.

        Returns:
            Path to the objectfile.
        '''
        sha = sha1(file.parent.as_posix().encode()).hexdigest()
        return self.outdir / sha / (file.name + '.stexobj')

    def load_from_objectfile(self, file: Path) -> Optional[StexObject]:
        ''' Loads the cached objectfile for <file> if it exists.

        Parameters:
            file: Path to source file.

        Returns:
            The precompiled objectfile.

        Raises:
            ObjectfileNotFoundError If the objectfile does not exist.
            ObjectfileIsCorruptedError: If the loaded object file can not be deserialized.
        '''
        objectfile = self.get_objectfile_path(file)
        if not objectfile.is_file():
            raise ObjectfileNotFoundError(file)
        with open(objectfile, 'rb') as fd:
            obj = pickle.load(fd)
            if not isinstance(obj, StexObject):
                raise ObjectfileIsCorruptedError(f'Objectfile for "{file}" is corrupted.')
            return obj

    def recompilation_required(self, file: Path, time_modified: float = None):
        ''' Tests if compilation required by checking if the objectfile is up to date.

        Parameters:
            file: Valid path to a source file.
            time_modified: Some external time of last modification that overrides the objectfile's time. (Range of time.time())

        Returns:
            Returns true if the file wasnt compiled yet or if the objectfile is older than the last edit to the file.
        '''
        objectfile = self.get_objectfile_path(file)
        if not objectfile.is_file():
            return True
        time_compiled = objectfile.lstat().st_mtime
        if time_modified and time_compiled < time_modified:
            return True
        if time_compiled < file.lstat().st_mtime:
            return True
        return False

    def compile(self, file: Path, content: str = None, dryrun: bool = False) -> StexObject:
        """ Compiles a single stex latex file into a objectfile.

        The compiled stex object will be stored into the provided outdir.

        Parameters:
            file: Path to sourcefile.
            content: Content of the file. If given, the file will be compiled using this content.
            dryrun: Do not store objectfiles in outdir after compiling.

        Returns:
            The compiled stex object.

        Raises:
            FileNotFoundError: If the source file is not a file.
        """
        file = file.expanduser().resolve().absolute()
        if not file.is_file():
            raise FileNotFoundError(file)
        objectfile = self.get_objectfile_path(file)
        objectdir = objectfile.parent
        objectdir.mkdir(parents=True, exist_ok=True)
        object = StexObject(file)
        parser = IntermediateParser(file)
        parser.parse(content, self.model)
        if parser.tags:
            for token, label in parser.tags:
                object.diagnostics.trefier_tag(token.range, token.text, label)
        for loc, errors in parser.errors.items():
            for err in errors:
                object.diagnostics.parser_exception(loc.range, err)
        for root in parser.roots:
            root: IntermediateParseTree
            context: List[Tuple[IntermediateParseTree, Symbol]] = [(None, object.symbol_table)]
            enter = functools.partial(self._compile_enter, object, context)
            exit = functools.partial(self._compile_exit, object, context)
            root.traverse(enter, exit)
        try:
            if not dryrun:
                with open(objectfile, 'wb') as fd:
                    pickle.dump(object, fd)
        except:
            # ignore errors if objectfile can't be written to disk
            # and continue as usual
            log.exception('Failed to write object in "%s" to "%s".', file, objectfile)
        return object

    def _compile_modsig(self, obj: StexObject, context: Symbol, modsig: ModsigIntermediateParseTree):
        if not isinstance(context, RootSymbol):
            # TODO: Semantic location check
            obj.diagnostics.parent_must_be_root_semantic_location_check(modsig.location.range, 'modsig')
        name_location = modsig.location.replace(positionOrRange=modsig.name.range)
        if obj.file.stem != modsig.name.text:
            obj.diagnostics.file_name_mismatch(modsig.location.range, modsig.name.text, obj.file.stem)
        module = ModuleSymbol(
            module_type=ModuleType.MODSIG,
            location=name_location,
            name=modsig.name.text)
        try:
            context.add_child(module)
            return module
        except DuplicateSymbolDefinedError:
            log.exception('%s: Failed to compile modsig %s.', module.location.format_link(), module.name)
        return None

    def _compile_modnl(self, obj: StexObject, context: Symbol, modnl: ModnlIntermediateParseTree):
        if not isinstance(context, RootSymbol):
            # TODO: Semantic location check
            obj.diagnostics.parent_must_be_root_semantic_location_check(modnl.location.range, 'modnl')
        expected_file_stem = f'{modnl.name.text}.{modnl.lang.text}'
        if obj.file.stem != expected_file_stem:
            obj.diagnostics.file_name_mismatch(modnl.location.range, expected_file_stem, obj.file.stem)
        binding = BindingSymbol(modnl.location, modnl.name.text, modnl.lang)
        try:
            context.add_child(binding)
        except DuplicateSymbolDefinedError:
            log.exception('%s: Failed to compile language binding of %s.', modnl.location.format_link(), modnl.name.text)
            return None
        # Important, the context must be changed here to the binding, else the dependency and reference won't be resolved correctly
        context = binding
        # Add dependency to the file the module definition must be located in
        dep = Dependency(
            range=modnl.name.range,
            scope=context,
            module_name=modnl.name.text,
            module_type_hint=ModuleType.MODSIG,
            file_hint=modnl.path,
            export=True)
        obj.add_dependency(dep)
        # Add the reference from the module name to the parent module
        ref = Reference(modnl.name.range, context, [modnl.name.text], ReferenceType.MODSIG)
        obj.add_reference(ref)
        return binding

    def _compile_module(self, obj: StexObject, context: Symbol, module: ModuleIntermediateParseTree):
        if not isinstance(context, RootSymbol):
            # TODO: Semantic location check
            obj.diagnostics.parent_must_be_root_semantic_location_check(module.location.range, 'module')
        if module.id:
            name_location = module.location.replace(positionOrRange=module.id.range)
            symbol = ModuleSymbol(ModuleType.MODULE, name_location, module.id.text)
        else:
            symbol = ModuleSymbol(ModuleType.MODULE, module.location, name=None)
        try:
            context.add_child(symbol)
            return symbol
        except DuplicateSymbolDefinedError:
            log.exception('%s: Failed to compile module %s.', module.location.format_link(), module.id.text)
        return None

    def _compile_tassign(self, obj: StexObject, context: Symbol, tassign: TassignIntermediateParseTree):
        if not isinstance(tassign.parent, ViewSigIntermediateParseTree):
            obj.diagnostics.semantic_location_check(tassign.location.range, tassign.torv + 'assign', 'Only allowed inside "gviewsig"')
            return
        view : ViewSigIntermediateParseTree = tassign.parent

        obj.add_reference(Reference(tassign.source_symbol.range, context, [view.source_module.text, tassign.source_symbol.text], ReferenceType.DEF))
        if tassign.torv == 'v':
            obj.add_reference(Reference(tassign.target_term.range, context, [view.target_module.text, tassign.target_term.text], ReferenceType.DEF))

    def _compile_trefi(self, obj: StexObject, context: Symbol, trefi: TrefiIntermediateParseTree):
        if trefi.drefi:
            # TODO: Semantic location check
            module: ModuleSymbol = context.get_current_module()
            if not module:
                obj.diagnostics.module_not_found_semantic_location_check(trefi.location.range, 'drefi')
            else:
                try:
                    symbol = DefSymbol(
                        DefType.DREF,
                        trefi.location,
                        trefi.name,
                        access_modifier=context.get_visible_access_modifier())
                    module.add_child(symbol, alternative=True)
                except InvalidSymbolRedifinitionException as err:
                    obj.diagnostics.invalid_redefinition(trefi.location.range, err.other_location, err.info)
        if trefi.module:
            # TODO: Semantic location check
            obj.add_reference(Reference(trefi.module.range, context, [trefi.module.text], ReferenceType.MODSIG | ReferenceType.MODULE))
            obj.add_reference(Reference(trefi.location.range, context, [trefi.module.text, trefi.name], ReferenceType.ANY_DEFINITION))
        else:
            # TODO: Semantic location check
            module_name: str = trefi.find_parent_module_name()
            obj.add_reference(Reference(trefi.location.range, context, [module_name, trefi.name], ReferenceType.ANY_DEFINITION))
        if trefi.m:
            obj.diagnostics.mtref_deprecated_check(trefi.location.range)
            has_q = trefi.target_annotation and '?' in trefi.target_annotation.text
            if not has_q:
                obj.diagnostics.mtref_questionmark_syntax_check(trefi.location.range)

    def _compile_defi(self, obj: StexObject, context: Symbol, defi: DefiIntermediateParseTree):
        current_module = context.get_current_module()
        if current_module:
            # TODO: Semantic location check
            symbol = DefSymbol(
                DefType.DEF,
                defi.location,
                defi.name,
                access_modifier=context.get_visible_access_modifier())
            try:
                # TODO: alternative definition possibly allowed here?
                current_module.add_child(symbol)
            except DuplicateSymbolDefinedError as err:
                obj.diagnostics.duplicate_symbol_definition(symbol.location.range, err.name, err.previous_location)
        else:
            if not defi.find_parent_module_name():
                # TODO: Semantic location check
                # A defi without a parent module doesn't generate a reference
                obj.diagnostics.module_not_found_semantic_location_check(defi.location.range, 'defi')
                return
            obj.add_reference(
                Reference(
                    range=defi.location.range,
                    scope=context,
                    name=[defi.find_parent_module_name(), defi.name],
                    reference_type=ReferenceType.ANY_DEFINITION))

    def _compile_sym(self, obj: StexObject, context: Symbol, sym: SymIntermediateParserTree):
        current_module = context.get_current_module()
        if not current_module:
            # TODO: Semantic location check
            obj.diagnostics.module_not_found_semantic_location_check(sym.location.range, 'sym')
            return
        symbol = DefSymbol(
            DefType.SYM,
            sym.location,
            sym.name,
            noverb=sym.noverb.is_all,
            noverbs=sym.noverb.langs,
            access_modifier=context.get_visible_access_modifier())
        try:
            current_module.add_child(symbol)
        except DuplicateSymbolDefinedError as err:
            obj.diagnostics.duplicate_symbol_definition(symbol.location.range, err.name, err.previous_location)

    def _compile_symdef(self, obj: StexObject, context: Symbol, symdef: SymdefIntermediateParseTree):
        current_module = context.get_current_module()
        if not current_module:
            # TODO: Semantic location check
            obj.diagnostics.module_not_found_semantic_location_check(symdef.location.range, 'symdef')
            return
        symbol = DefSymbol(
            DefType.SYMDEF,
            symdef.location,
            symdef.name.text,
            noverb=symdef.noverb.is_all,
            noverbs=symdef.noverb.langs,
            access_modifier=context.get_visible_access_modifier())
        try:
            current_module.add_child(symbol, alternative=True)
        except InvalidSymbolRedifinitionException as err:
            obj.diagnostics.invalid_redefinition(symbol.location.range, err.other_location, err.info)

    def _compile_importmodule(self, obj: StexObject, context: Symbol, importmodule: ImportModuleIntermediateParseTree):
        if not isinstance(importmodule.find_parent_module_parse_tree(), ModuleIntermediateParseTree):
            # TODO: Semantic location check: importmodule only allowed inside begin{module}?
            obj.diagnostics.module_not_found_semantic_location_check(importmodule.location.range, 'importmodule')
        dep = Dependency(
            range=importmodule.location.range,
            scope=context,
            module_name=importmodule.module.text,
            module_type_hint=ModuleType.MODULE,
            file_hint=importmodule.path_to_imported_file(self.root_dir),
            export=importmodule.export) #TODO: Is usemodule exportet?
        obj.add_dependency(dep)
        ref = Reference(importmodule.location.range, context, [importmodule.module.text], ReferenceType.MODULE)
        obj.add_reference(ref)
        if importmodule.repos:
            obj.diagnostics.replace_repos_with_mhrepos(importmodule.repos.range)
        # TODO: is-current-dir-check not needed? importmodule{} without any arg --> SAME FILE (not same directory like with gmodule)
        # importmodule[]{} with any arg (mhrepos, path, dir) --> SAME DIRECTORY (if the arg is the same directory) but not same file
        if importmodule.mhrepos and importmodule.mhrepos.text == util.get_repository_name(self.root_dir, obj.file):
            obj.diagnostics.is_current_dir_check(importmodule.mhrepos.range, importmodule.mhrepos.text)
        if importmodule.path and importmodule.path.text == util.get_path(self.root_dir, obj.file):
            obj.diagnostics.is_current_dir_check(importmodule.path.range, importmodule.path.text)
        if importmodule.dir and importmodule.dir.text == util.get_dir(self.root_dir, obj.file).as_posix():
            obj.diagnostics.is_current_dir_check(importmodule.dir.range, importmodule.dir.text)

    def _compile_gimport(self, obj: StexObject, context: Symbol, gimport: GImportIntermediateParseTree):
        if not isinstance(gimport.find_parent_module_parse_tree(), (ModuleIntermediateParseTree, ModsigIntermediateParseTree)):
            # TODO: Semantic location check
            obj.diagnostics.module_not_found_semantic_location_check(gimport.location.range, 'gimport')
        dep = Dependency(
            range=gimport.location.range,
            scope=context,
            module_name=gimport.module.text,
            module_type_hint=ModuleType.MODSIG,
            file_hint=gimport.path_to_imported_file(self.root_dir),
            export=True)
        obj.add_dependency(dep)
        ref = Reference(dep.range, context, [dep.module_name], ReferenceType.MODSIG)
        obj.add_reference(ref)
        if gimport.repository and gimport.repository.text == util.get_repository_name(self.root_dir, gimport.location.path):
            obj.diagnostics.is_current_dir_check(gimport.repository.range, gimport.repository.text)

    def _compile_scope(self, obj: StexObject, context: Symbol, tree: ScopeIntermediateParseTree):
        # TODO: Semantic location check
        scope = ScopeSymbol(tree.location, name=tree.scope_name.text)
        context.add_child(scope)
        return scope

    def _compile_gstructure(self, obj: StexObject, context: Symbol, tree: GStructureIntermediateParseTree):
        # TODO: Compile gstructure and return either a Scope symbol or create a new GStructureSymbol class.
        # TODO: If content of the gstructure environment is not important, do not return anything, and delete the "next_context = " line in Compiler._enter.

        # Hint: Da gstrucutre nur als toplevel vorkommen kann, sollte für den context immer gelten context.name == '__root__'.
        return None

    def _compile_view(self, obj: StexObject, context: Symbol, view: ViewIntermediateParseTree):
        if not isinstance(context, RootSymbol):
            # TODO: Semantic location check
            obj.diagnostics.parent_must_be_root_semantic_location_check(view.location.range, 'view')

        if view.env == 'gviewnl':
            expected_name = f'{view.module.text}.{view.lang.text}'
            if expected_name != obj.file.stem:
                obj.diagnostics.file_name_mismatch(view.module.range, expected_name, obj.file.stem)

        if view.env == 'gviewnl':
            source_file_hint = GImportIntermediateParseTree.build_path_to_imported_module(self.root_dir,
                view.location.path, view.fromrepos.text if view.fromrepos else None, view.source_module.text)
            target_file_hint = GImportIntermediateParseTree.build_path_to_imported_module(self.root_dir,
                view.location.path, view.torepos.text if view.torepos else None, view.target_module.text)
        elif view.env == 'mhview':
            source_file_hint = ImportModuleIntermediateParseTree.build_path_to_imported_module(self.root_dir,
                view.location.path, view.fromrepos.text if view.fromrepos else None, view.frompath.text if view.frompath else None, None, None, view.source_module.text)
            target_file_hint = ImportModuleIntermediateParseTree.build_path_to_imported_module(self.root_dir,
                view.location.path, view.torepos.text if view.torepos else None, view.topath.text if view.topath else None, None, None, view.target_module.text)
        else:
            raise CompilerError(f'Unexpected environment: "{view.env}"')

        source_dep = Dependency(
            range=view.source_module.range,
            scope=context,
            module_name=view.source_module.text,
            module_type_hint=ModuleType.MODSIG, # TODO: Dependency module type hint as a flag (so we can do MODSIG | MODULE)
            file_hint=source_file_hint,
            export=True)
        obj.add_dependency(source_dep)
        ref = Reference(source_dep.range, context, [source_dep.module_name], ReferenceType.MODSIG | ReferenceType.MODULE)
        obj.add_reference(ref)

        target_dep = Dependency(
            range=view.target_module.range,
            scope=context,
            module_name=view.target_module.text,
            module_type_hint=ModuleType.MODSIG, # TODO: Dependency module type hint as a flag (so we can do MODSIG | MODULE)
            file_hint=target_file_hint,
            export=True)
        obj.add_dependency(target_dep)
        ref = Reference(target_dep.range, context, [target_dep.module_name], ReferenceType.MODSIG | ReferenceType.MODULE)
        obj.add_reference(ref)

        return None

    def _compile_viewsig(self, obj: StexObject, context: Symbol, viewsig: ViewSigIntermediateParseTree):
        if not isinstance(context, RootSymbol):
            # TODO: Semantic location check
            obj.diagnostics.parent_must_be_root_semantic_location_check(viewsig.location.range)

        if viewsig.module.text != obj.file.stem:
            obj.diagnostics.file_name_mismatch(viewsig.module.range, viewsig.module.text, obj.file.stem)

        source_dep = Dependency(
            range=viewsig.source_module.range,
            scope=context,
            module_name=viewsig.source_module.text,
            module_type_hint=ModuleType.MODSIG,  # TODO: Dependency module type hint as a flag (so we can do MODSIG | MODULE)
            file_hint=GImportIntermediateParseTree.build_path_to_imported_module(self.root_dir, viewsig.location.path, viewsig.fromrepos.text if viewsig.fromrepos else None, viewsig.source_module.text),
            export=True)
        obj.add_dependency(source_dep)
        ref = Reference(source_dep.range, context, [source_dep.module_name], ReferenceType.MODSIG | ReferenceType.MODULE)
        obj.add_reference(ref)

        target_dep = Dependency(
            range=viewsig.target_module.range,
            scope=context,
            module_name=viewsig.target_module.text,
            module_type_hint=ModuleType.MODSIG,
            file_hint=GImportIntermediateParseTree.build_path_to_imported_module(self.root_dir, viewsig.location.path, viewsig.torepos.text if viewsig.torepos else None, viewsig.target_module.text),
            export=True)
        obj.add_dependency(target_dep)
        ref = Reference(target_dep.range, context, [target_dep.module_name], ReferenceType.MODSIG | ReferenceType.MODULE)
        obj.add_reference(ref)

        return None

    def _compile_enter(self, obj: StexObject, context: List[Tuple[IntermediateParseTree, Symbol]], tree: IntermediateParseTree):
        """ This manages the enter operation of the intermediate parse tree into relevant environemnts.

        Each relevant intermediate environment is compiled here and compile operations of environments that are in \\begin{} & \\end{}
        tags usually return a new context symbol that allows for other compile operations that are executed before this one
        is exited, to attach the inner symbols to that context.
        """
        _, current_context = context[-1]
        next_context = None
        if isinstance(tree, ScopeIntermediateParseTree):
            next_context = self._compile_scope(obj, current_context, tree)
        elif isinstance(tree, ModsigIntermediateParseTree):
            next_context = self._compile_modsig(obj, current_context, tree)
        elif isinstance(tree, ModnlIntermediateParseTree):
            next_context = self._compile_modnl(obj, current_context, tree)
        elif isinstance(tree, ModuleIntermediateParseTree):
            next_context = self._compile_module(obj, current_context, tree)
        elif isinstance(tree, TassignIntermediateParseTree):
            self._compile_tassign(obj, current_context, tree)
        elif isinstance(tree, TrefiIntermediateParseTree):
            self._compile_trefi(obj, current_context, tree)
        elif isinstance(tree, DefiIntermediateParseTree):
            self._compile_defi(obj, current_context, tree)
        elif isinstance(tree, SymIntermediateParserTree):
            self._compile_sym(obj, current_context, tree)
        elif isinstance(tree, SymdefIntermediateParseTree):
            self._compile_symdef(obj, current_context, tree)
        elif isinstance(tree, ImportModuleIntermediateParseTree):
            self._compile_importmodule(obj, current_context, tree)
        elif isinstance(tree, GImportIntermediateParseTree):
            self._compile_gimport(obj, current_context, tree)
        elif isinstance(tree, GStructureIntermediateParseTree):
            # TODO: Remove "next_context = " in case that gstructure doesn't return a symbol
            next_context = self._compile_gstructure(obj, current_context, tree)
        elif isinstance(tree, ViewIntermediateParseTree):
            next_context = self._compile_view(obj, current_context, tree)
        elif isinstance(tree, ViewSigIntermediateParseTree):
            next_context = self._compile_viewsig(obj, current_context, tree)
        if next_context:
            context.append((tree, next_context))

    def _compile_exit(self, obj: StexObject, context: List[Tuple[IntermediateParseTree, Symbol]], tree: IntermediateParseTree):
        " This manages the symbol table context structure, nothing should be done here. Everytime the tree that opened a new context symbol is exited, the context symbol must be replaced as well. "
        current_context_tree, _ = context[-1]
        if current_context_tree == tree:
            context.pop()
