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
from typing import Dict, List, Tuple
from pathlib import Path
from hashlib import sha1
import datetime
import difflib
import pickle
import functools
import logging
from time import time
from enum import Flag

log = logging.getLogger(__name__)

from stexls.vscode import Position, Range, Location
from stexls.util.format import format_enumeration

from .parser import *
from .symbols import *
from .exceptions import *
from . import util

__all__ = ['Compiler', 'StexObject', 'Dependency', 'Reference', 'ReferenceType']

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


class ReferenceType(Flag):
    """ The reference type is the expected type of the symbol pointed to by a reference.

    The statement used to generate the reference usually knows which types of symbols
    are expected. After the reference is resolved the symbol type and expected reference
    type can be compared in order to detect errors.
    """
    MODULE=1
    MODSIG=2
    DEF=4
    BINDING=8

    def format_enum(self):
        ' Formats the flag as a list in case multiple are possible like: "module" or "modsig" for ReferenceType.MODULE|MODSIG '
        l = []
        for exp in range(0, 3):
            mask = 2**exp
            if self.value & mask:
                l.append(ReferenceType(mask).name.lower())
        return format_enumeration(l, last='or')


class Reference:
    ' Container that contains information about which symbol is referenced by name. '
    def __init__(self, range: Range, scope: Symbol, name: List[str], reference_type: ReferenceType):
        """ Initializes the reference container.

        Parameters:
            range: Location at which the reference is created.
            scope: The parent symbol which contains range. Used to create error messages.
            name: Path to the symbol.
            reference_type: Expected type of the resolved symbol.
                Hint: The reference type can be or'd together to create more complex references.
        """
        assert range is not None
        assert name is not None
        assert all(isinstance(i, str) for i in name)
        self.range = range
        self.scope = scope
        self.name = name
        self.reference_type: ReferenceType = reference_type

    def __repr__(self):
        return f'[Reference  "{"?".join(self.name)}" of type {self.reference_type.format_enum()} at {self.range.start.format()}]'


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
        # Accumulator for errors that occured at <range> of this file.
        self.errors: Dict[Range, List[Exception]] = dict()
        # Stores creation time
        self.creation_time = time()

    def find_similar_symbols(self, qualified: List[str], ref_type: ReferenceType) -> List[str]:
        ' Find simlar symbols with reference to a qualified name and an expected symbol type. '
        names = []
        def f(symbol: Symbol):
            if isinstance(symbol, DefSymbol):
                if ReferenceType.DEF in ref_type:
                    names.append('?'.join(symbol.qualified))
            elif isinstance(symbol, ModuleSymbol):
                if ReferenceType.MODSIG in ref_type or ReferenceType.MODULE in ref_type:
                    names.append('?'.join(symbol.qualified))
        self.symbol_table.traverse(lambda s: f(s))
        return difflib.get_close_matches('?'.join(qualified), names)

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
        f += '\nErrors:'
        if self.errors:
            for r, errs in self.errors.items():
                loc = Location(self.file.as_uri(), r).format_link()
                for err in errs:
                    f += f'\n\t{loc}: {err}'
        else:
                   f += '\n\tNo errors.'
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
            if dep0.check_if_same_module_imported(dep):
                # Skip adding this dependency
                location = Location(self.file.as_uri(), dep0.range)
                self.errors.setdefault(dep.range, []).append(
                    Warning(f'Redundant import of module "{dep.module_name}" at "{location.format_link()}"'))
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

    The idea is that "c++ main.cpp -c -o outdir/main.o" is equal to "Compiler(., outdir).compile(main.tex)"
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

    def get_objectfile_path(self, file: Path) -> Path:
        ' Returns the path to where the objectfile should be cached. '
        # TODO: This maybe should not be part of the compiler class, but instead some kind of manager class, that manages storage of objectfiles
        sha = sha1(file.parent.as_posix().encode()).hexdigest()
        return self.outdir / sha / (file.name + '.stexobj')

    def load_from_objectfile(self, file: Path) -> Optional[StexObject]:
        ' Loads the cached objectfile for <file> if it exists. '
        objectfile = self.get_objectfile_path(file)
        if not objectfile.is_file():
            return None
        with open(objectfile, 'rb') as fd:
            obj = pickle.load(fd)
            if not isinstance(obj, StexObject):
                raise Exception(f'Objectfile for "{file}" is corrupted.')
            return obj

    def recompilation_required(self, file: Path, time_modified: float = None):
        ''' Tests if compilation required by checking if the objectfile is up to date.

        Parameters:
            file: Path to sourcefile
            time_modified: Some external time of last modification that overrides the objectfile's time. (Range of time.time())

        Returns:
            Returns true if the file wasnt compiled yet or if the objectfile is older than the last edit to the file.
        '''
        objectfile = self.get_objectfile_path(file)
        if not objectfile.is_file():
            return True
        mtime = objectfile.lstat().st_mtime
        if time_modified and mtime < time_modified:
            return True
        if file.is_file() and mtime < file.lstat().st_mtime:
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
        for loc, err in parser.errors:
            object.errors[loc.range] = err
        parser.parse(content)
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
            obj.errors.setdefault(modsig.location.range, []).append(
                CompilerError(f'Invalid modsig location: Parent is not root'))
        name_location = modsig.location.replace(positionOrRange=modsig.name.range)
        if obj.file.name != f'{modsig.name.text}.tex':
            obj.errors.setdefault(name_location.range, []).append(
                CompilerWarning(f'Invalid modsig filename: Expected "{modsig.name.text}.tex"'))
        module = ModuleSymbol(
            module_type=ModuleType.MODSIG,
            location=name_location,
            name=modsig.name.text)
        try:
            context.add_child(module)
            return module
        except DuplicateSymbolDefinedException:
            log.exception('%s: Failed to compile modsig %s.', module.location.format_link(), module.name)
        return None

    def _compile_modnl(self, obj: StexObject, context: Symbol, modnl: ModnlIntermediateParseTree):
        if not isinstance(context, RootSymbol):
            # TODO: Semantic location check
            obj.errors.setdefault(modnl.location.range, []).append(
                CompilerError(f'Invalid modnl location: Parent is not root'))
        if obj.file.name != f'{modnl.name.text}.{modnl.lang.text}.tex':
            obj.errors.setdefault(modnl.location.range, []).append(CompilerWarning(f'Invalid modnl filename: Expected "{modnl.name.text}.{modnl.lang.text}.tex"'))
        binding = BindingSymbol(modnl.location, modnl.name.text, modnl.lang)
        try:
            context.add_child(binding)
        except DuplicateSymbolDefinedException:
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
            obj.errors.setdefault(module.location.range, []).append(
                CompilerError(f'Invalid module location: Parent is not root'))
        if module.id:
            name_location = module.location.replace(positionOrRange=module.id.range)
            symbol = ModuleSymbol(ModuleType.MODULE, name_location, module.id.text)
        else:
            symbol = ModuleSymbol(ModuleType.MODULE, module.location, name=None)
        try:
            context.add_child(symbol)
            return symbol
        except DuplicateSymbolDefinedException:
            log.exception('%s: Failed to compile module %s.', module.location.format_link(), module.id.text)
        return None

    def _compile_trefi(self, obj: StexObject, context: Symbol, trefi: TrefiIntermediateParseTree):
        if trefi.drefi:
            # TODO: Semantic location check
            module: ModuleSymbol = context.get_current_module()
            if not module:
                obj.errors.setdefault(trefi.location.range, []).append(
                    CompilerWarning('Invalid drefi location: Parent module symbol not found.'))
            else:
                try:
                    symbol = DefSymbol(
                        DefType.DREF,
                        trefi.location,
                        trefi.name,
                        access_modifier=context.get_visible_access_modifier())
                    module.add_child(symbol, alternative=True)
                except InvalidSymbolRedifinitionException as err:
                    obj.errors.setdefault(trefi.location.range, []).append(err)
        if trefi.module:
            # TODO: Semantic location check
            obj.add_reference(Reference(trefi.module.range, context, [trefi.module.text], ReferenceType.MODSIG | ReferenceType.MODULE))
            obj.add_reference(Reference(trefi.location.range, context, [trefi.module.text, trefi.name], ReferenceType.DEF))
        else:
            # TODO: Semantic location check
            module_name: str = trefi.find_parent_module_name()
            obj.add_reference(Reference(trefi.location.range, context, [module_name, trefi.name], ReferenceType.DEF))
        if trefi.m:
            obj.errors.setdefault(trefi.location.range, []).append(
                DeprecationWarning('mtref environments are deprecated.'))
            has_q = trefi.target_annotation and '?' in trefi.target_annotation.text
            if not has_q:
                obj.errors.setdefault(trefi.location.range, []).append(
                    CompilerError('Invalid "mtref" environment: Target symbol must be clarified by using "?<symbol>" syntax.'))

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
            except DuplicateSymbolDefinedException as err:
                obj.errors.setdefault(symbol.location.range, []).append(err)
        else:
            if not defi.find_parent_module_name():
                # TODO: Semantic location check
                # A defi without a parent module doesn't generate a reference
                obj.errors.setdefault(defi.location.range, []).append(
                    CompilerError(f'Invalid defi: "{defi.name}" does not have a module.'))
                return
            obj.add_reference(
                Reference(
                    range=defi.location.range,
                    scope=context,
                    name=[defi.find_parent_module_name(), defi.name],
                    reference_type=ReferenceType.DEF))

    def _compile_sym(self, obj: StexObject, context: Symbol, sym: SymIntermediateParserTree):
        current_module = context.get_current_module()
        if not current_module:
            # TODO: Semantic location check
            obj.errors.setdefault(sym.location.range, []).append(
                CompilerError(f'Invalid location: "{sym.name}" does not have a module.'))
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
        except DuplicateSymbolDefinedException as err:
            obj.errors.setdefault(symbol.location.range, []).append(err)

    def _compile_symdef(self, obj: StexObject, context: Symbol, symdef: SymdefIntermediateParseTree):
        current_module = context.get_current_module()
        if not current_module:
            # TODO: Semantic location check
            obj.errors.setdefault(symdef.location.range, []).append(
                CompilerError(f'Invalid location: "{symdef.name.text}" does not have a module.'))
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
            obj.errors.setdefault(symbol.location.range, []).append(err)

    def _compile_importmodule(self, obj: StexObject, context: Symbol, importmodule: ImportModuleIntermediateParseTree):
        if not isinstance(importmodule.find_parent_module_parse_tree(), ModuleIntermediateParseTree):
            # TODO: Semantic location check: importmodule only allowed inside begin{module}?
            obj.errors.setdefault(importmodule.location.range, []).append(
                CompilerError(f'Invalid importmodule location: module environment not found.'))
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
            obj.errors.setdefault(importmodule.repos.range, []).append(
                DeprecationWarning('Argument "repos" is deprecated and should be replaced with "mhrepos".'))
        if importmodule.mhrepos and importmodule.mhrepos.text == util.get_repository_name(self.root_dir, obj.file):
            obj.errors.setdefault(importmodule.mhrepos.range, []).append(
                Warning(f'Redundant mhrepos key: "{importmodule.mhrepos.text}" is the current repository.'))
        if importmodule.path and importmodule.path.text == util.get_path(self.root_dir, obj.file):
            obj.errors.setdefault(importmodule.path.range, []).append(
                Warning(f'Redundant path key: "{importmodule.path.text}" is the current path.'))
        if importmodule.dir and importmodule.dir.text == util.get_dir(self.root_dir, obj.file).as_posix():
            obj.errors.setdefault(importmodule.location.range, []).append(
                Warning(f'Targeted dir "{importmodule.dir.text}" is the current dir.'))

    def _compile_gimport(self, obj: StexObject, context: Symbol, gimport: GImportIntermediateParseTree):
        if not isinstance(gimport.find_parent_module_parse_tree(), (ModuleIntermediateParseTree, ModsigIntermediateParseTree)):
            # TODO: Semantic location check
            obj.errors.setdefault(gimport.location.range, []).append(
                CompilerError(f'Invalid gimport location: module or modsig environment not found.'))
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
            obj.errors.setdefault(gimport.repository.range, []).append(
                Warning(f'Redundant repository specified: "{gimport.repository.text}" is the current repository.'))

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

    def _compile_view(self, obj: StexObject, context: Symbol, tree: ViewIntermediateParseTree):
        # TODO: Compile view and return either a Scope symbol or create a new ViewSymbol class.

        # Hint: Da view nur als toplevel vorkommen kann, sollte für den context immer gelten context.name == '__root__'.
        return None

    def _compile_viewsig(self, obj: StexObject, context: Symbol, tree: ViewSigIntermediateParseTree):
        # TODO: Compile viewsig and return either a Scope symbol or create a new ViewSigSymbol class.

        # Hint: Da viewsig nur als toplevel vorkommen kann, sollte für den context immer gelten context.name == '__root__'.
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
