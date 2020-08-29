from __future__ import annotations
from typing import Dict, Optional, Set, Union, Iterable, Callable, List, Tuple
from pathlib import Path
from collections import defaultdict
from hashlib import sha1
import difflib
import multiprocessing
import pickle
import itertools
import functools
import glob
import logging
from enum import Flag

log = logging.getLogger(__name__)

from stexls.vscode import DocumentUri, Position, Range, Location
from stexls.util.workspace import Workspace
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

    def check_if_same_module_imported(self, other: Dependency):
        if self.module_name == other.module_name:
            if self.scope == other.scope or self.scope.is_parent_of(other.scope):
                return True
        return False

    def __repr__(self):
        return f'[Dependency at={self.range} module={self.module_name} type={self.module_type_hint} file="{self.file_hint}" export={self.export}]'


class ReferenceType(Flag):
    MODULE=1
    MODSIG=2
    DEF=4

    def format_enum(self):
        l = []
        for exp in range(0, 3):
            mask = 2**exp
            if self.value & mask:
                l.append(ReferenceType(mask).name.lower())
        return format_enumeration(l, last='or')


class Reference:
    def __init__(self, range: Range, scope: Symbol, name: Iterable[str], reference_type: ReferenceType):
        self.range = range
        self.scope = scope
        self.name = name
        self.reference_type: ReferenceType = reference_type

    def __repr__(self): return f'[Reference {self.reference_type.name} "{self.name}" at {self.range}]'


class StexObject:
    def __init__(self, file: Path):
        # Path to source file from which this object is generated
        self.file = file
        # Symbol table with definitions: Key is symbol name for easy search access by symbol name
        self.symbol_table: Symbol = Symbol(None, '__root__')
        # Dict of the ranges at which a dependency was create to the dependency that was created there.
        self.dependencies: List[Dependency] = list()
        # List of references. A reference consists of a range relative to the file that owns the reference and the referenced file or symbol identifier.
        self.references: List[Reference] = list()
        # Accumulator for errors that occured at <range> of this file.
        self.errors: Dict[Range, List[Exception]] = dict()

    def find_similar_symbols(self, qualified: List[str], ref_type: ReferenceType) -> List[str]:
        ' Find simlar symbols with reference to a qualified name and an expected symbol type. '
        names = []
        def f(ref_type: ReferenceType, names: List[str], symbol: Symbol):
            if isinstance(symbol, DefSymbol):
                if ReferenceType.DEF in ref_type:
                    names.append('?'.join(symbol.qualified[-2:]))
            elif isinstance(symbol, ModuleSymbol):
                if ReferenceType.MODSIG in ref_type or ReferenceType.MODULE in ref_type:
                    names.append('?'.join(symbol.qualified[-2:]))
        self.symbol_table.traverse(lambda s: f(ref_type, names, s))
        return difflib.get_close_matches('?'.join(qualified), names)

    def format(self):
        f = f'\nFile: "{self.file}"'
        f += '\nDependencies:'
        if self.dependencies:
            for dep in self.dependencies:
                loc = Location(self.file.as_uri(), dep.range).format_link()
                f += f'\n\t{loc}: {dep.module_name} from "{dep.file_hint}"'
        else:
            f += 'n\tNo dependencies.'
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
            l.append(f'{"-"*s.depth}> {s}')
        self.symbol_table.traverse(lambda s: enter(l, s))
        f += '\n' + '\n'.join(l)
        print(f)

    def add_dependency(self, dep: Dependency):
        """ Registers a dependency that the owner file has to the in the dependency written file and module.

        Parameters:
            dep: Information about the dependency.
        """
        for dep0 in self.dependencies:
            if dep0.check_if_same_module_imported(dep):
                # Skip adding this dependency
                location = Location(self.file.as_uri(), dep0.range)
                self.errors.setdefault(dep.range, []).append(
                    Warning(f'Import of same modue "{dep.module_name}" at "{location.format_link()}"'))
                return
        self.dependencies.append(dep)

    def add_reference(self, reference: Reference):
        """ Registers a reference.

        Parameters:
            reference: Information about the reference.
        """
        self.references.append(reference)


class Compiler:
    def __init__(self, workspace: Workspace, outdir: Path):
        # TODO: Having the workspace be part of the compiler may make multiprocessing too slow
        self.workspace = workspace
        self.outdir = outdir.expanduser().resolve().absolute()

    @staticmethod
    def compute_objectfile_path_hash(path: Path) -> str:
        ' Computes an hash from the path of a source file. '
        return sha1(path.parent.as_posix().encode()).hexdigest()

    @staticmethod
    def get_objectfile_path(outdir: Path, file: Path) -> Path:
        ' Returns the path to where the objectfile should be cached. '
        return outdir / Compiler.compute_objectfile_path_hash(file) / (file.name + '.stexobj')

    def recompilation_required(self, file: Path):
        ' Checks if sourcefile <file> should be recompiled based off of timestamps and whether an objectfile exists or not. '
        objectfile = Compiler.get_objectfile_path(self.outdir, file)
        return not objectfile.is_file() or objectfile.lstat().st_mtime < file.lstat().st_mtime

    def compile(self, file: Path) -> StexObject:
        """ Compiles a single stex latex file into a objectfile.

        The compiled stex object will be stored into the provided outdir.
        Compilation of the file will be skipped automatically and the object is loaded from disk,
        if the stored object file already exists and it's timestamp is from later then
        the last change to the file.

        Compilation of the file is forced if the workspace property of the compiler has
        the file registered as currently open. In that case, the content registered at the workspace object
        is used instead of reading the file from disk.

        Parameters:
            file: Path to sourcefile.

        Returns:
            The compiled stex object.

        Raises:
            FileNotFoundError: If the source file is not a file.
        """
        file = file.expanduser().resolve().absolute()
        if not file.is_file():
            raise FileNotFoundError(f'"{file}" is not a file.')
        objectfile = Compiler.get_objectfile_path(self.outdir, file)
        objectdir = objectfile.parent
        for _ in range(2): # give it two attempts to figure out whats going on
            content = self.workspace.read_file(file) if self.workspace.is_open(file) else None
            if content is not None or self.recompilation_required(file):
                # if not already compiled or the compiled object is old, create a new object
                objectdir.mkdir(parents=True, exist_ok=True)
                object = StexObject(file)
                parser = IntermediateParser(file)
                for loc, err in parser.errors:
                    object.errors[loc.range] = err
                parser.parse(content)
                for root in parser.roots:
                    root: IntermediateParseTree
                    symbol_stack: List[Symbol] = [object.symbol_table]
                    enter = functools.partial(self._compile_enter, object, symbol_stack)
                    exit = functools.partial(self._compile_exit, object, symbol_stack)
                    root.traverse(enter, exit)
                try:
                    with open(objectfile, 'wb') as fd:
                        pickle.dump(object, fd)
                except:
                    # ignore errors if objectfile can't be written to disk
                    # and continue as usual
                    log.exception('Failed to write object in "%s" to "%s".', file, objectfile)
                return object
            try:
                # else load from cached
                with open(objectfile, 'rb') as fd:
                    return pickle.load(fd)
            except:
                # if loading fails, attempt to delete the cachefile
                try:
                    if objectfile.is_file():
                        objectfile.unlink()
                except:
                    # ignore possible concurrent unlinks depending on if I do things concurrently later
                    pass
                # because this is a for loop, try again after deleting it

    def _compile_modsig(self, obj: StexObject, stack: List[Symbol], modsig: ModsigIntermediateParseTree):
        name_location = modsig.location.replace(positionOrRange=modsig.name.range)
        if obj.file.name != f'{modsig.name.text}.tex':
            obj.errors.setdefault(name_location.range, []).append(
                CompilerWarning(f'Invalid modsig filename: Expected "{modsig.name.text}.tex"'))
        module = ModuleSymbol(
            module_type=ModuleType.MODSIG,
            location=name_location,
            name=modsig.name.text)
        stack[-1].add_child(module)
        stack.append(module)

    def _compile_modnl(self, obj: StexObject, stack: List[Symbol], modnl: ModnlIntermediateParseTree):
        if obj.file.name != f'{modnl.name.text}.{modnl.lang.text}.tex':
            obj.errors.setdefault(modnl.location.range, []).append(CompilerWarning(f'Invalid modnl filename: Expected "{modnl.name.text}.{modnl.lang.text}.tex"'))
        # Add the reference from the module name to the parent module
        ref = Reference(modnl.name.range, stack[-1], [modnl.name.text], ReferenceType.MODSIG)
        obj.add_reference(ref)
        # Add dependency to the file the module definition must be located in
        dep = Dependency(
            range=modnl.name.range,
            scope=stack[-1],
            module_name=modnl.name.text,
            module_type_hint=ModuleType.MODSIG,
            file_hint=modnl.path,
            export=True)
        obj.add_dependency(dep)
        binding = BindingSymbol(modnl.location, modnl.name, modnl.lang)
        stack[-1].add_child(binding)
        stack.append(binding)

    def _compile_module(self, obj: StexObject, stack: List[Symbol], module: ModuleIntermediateParseTree):
        if module.id:
            name_location = module.location.replace(positionOrRange=module.id.range)
            symbol = ModuleSymbol(ModuleType.MODULE, name_location, module.id.text)
        else:
            symbol = ModuleSymbol(ModuleType.MODULE, module.location, name=None)
        stack[-1].add_child(symbol)
        stack.append(symbol)

    def _compile_trefi(self, obj: StexObject, stack: List[Symbol], trefi: TrefiIntermediateParseTree):
        if trefi.drefi:
            module: ModuleSymbol = stack[-1].get_current_module()
            if not module:
                obj.errors.setdefault(trefi.location.range, []).append(
                    CompilerWarning('Invalid drefi location: Parent module symbol not found.'))
            else:
                module.add_child(DefSymbol(DefType.DREF, trefi.location, trefi.name), alternative=True)
        if trefi.module:
            obj.add_reference(Reference(trefi.module.range, stack[-1], [trefi.module.text], ReferenceType.MODSIG | ReferenceType.MODULE))
            obj.add_reference(Reference(trefi.location.range, stack[-1], [trefi.module.text, trefi.name], ReferenceType.DEF))
        else:
            module_name: str = trefi.find_parent_module_name()
            obj.add_reference(Reference(trefi.location.range, stack[-1], [module_name, trefi.name], ReferenceType.DEF))
        if trefi.m:
            obj.errors.setdefault(trefi.location.range, []).append(
                DeprecationWarning('mtref environments are deprecated.'))
            has_q = trefi.target_annotation and '?' in trefi.target_annotation.text
            if not has_q:
                obj.errors.setdefault(trefi.location.range, []).append(
                    CompilerError('Invalid "mtref" environment: Target symbol must be clarified by using "?<symbol>" syntax.'))

    def _compile_defi(self, obj: StexObject, stack: List[Symbol], defi: DefiIntermediateParseTree):
        if isinstance(defi.find_parent_module_parse_tree(), ModuleIntermediateParseTree):
            symbol = DefSymbol(DefType.DEF, defi.location, defi.name)
            try:
                # TODO: alternative definition possibly allowed here?
                stack[-1].add_child(symbol)
            except DuplicateSymbolDefinedException as err:
                obj.errors.setdefault(symbol.location.range, []).append(err)
        else:
            obj.add_reference(
                Reference(
                    range=defi.location.range,
                    scope=stack[-1],
                    name=[defi.find_parent_module_name(), defi.name],
                    reference_type=ReferenceType.DEF))

    def _compile_sym(self, obj: StexObject, stack: List[Symbol], sym: SymIntermediateParserTree):
        symbol = DefSymbol(DefType.SYM, sym.location, sym.name, noverb=sym.noverb.is_all, noverbs=sym.noverb.langs)
        try:
            stack[-1].add_child(symbol)
        except DuplicateSymbolDefinedException as err:
            obj.errors.setdefault(symbol.location.range, []).append(err)

    def _compile_symdef(self, obj: StexObject, stack: List[Symbol], symdef: SymdefIntermediateParseTree):
        symbol = DefSymbol(
            DefType.SYMDEF,
            symdef.location,
            symdef.name.text,
            noverb=symdef.noverb.is_all,
            noverbs=symdef.noverb.langs)
        stack[-1].add_child(symbol, alternative=True)

    def _compile_importmodule(self, obj: StexObject, stack: List[Symbol], importmodule: ImportModuleIntermediateParseTree):
        # TODO: importmodule only allowed inside begin{module}?
        dep = Dependency(
            range=importmodule.location.range,
            scope=stack[-1],
            module_name=importmodule.module.text,
            module_type_hint=ModuleType.MODULE,
            file_hint=importmodule.path_to_imported_file(self.workspace.root),
            export=importmodule.export) #TODO: Is usemodule exportet?
        obj.add_dependency(dep)
        ref = Reference(importmodule.location.range, stack[-1], [importmodule.module.text], ReferenceType.MODULE)
        obj.add_reference(ref)
        if importmodule.repos:
            obj.errors.setdefault(importmodule.repos.range, []).append(
                DeprecationWarning('Argument "repos" is deprecated and should be replaced with "mhrepos".'))
        if importmodule.mhrepos and importmodule.mhrepos.text == util.get_repository_name(self.workspace.root, obj.file):
            obj.errors.setdefault(importmodule.mhrepos.range, []).append(
                Warning(f'Redundant mhrepos key: "{importmodule.mhrepos.text}" is the current repository.'))
        if importmodule.path and importmodule.path.text == util.get_path(self.workspace.root, obj.file):
            obj.errors.setdefault(importmodule.path.range, []).append(
                Warning(f'Redundant path key: "{importmodule.path.text}" is the current path.'))
        if importmodule.dir and importmodule.dir.text == util.get_dir(self.workspace.root, obj.file).as_posix():
            obj.errors.setdefault(importmodule.location.range, []).append(
                Warning(f'Targeted dir "{importmodule.dir.text}" is the current dir.'))

    def _compile_gimport(self, obj: StexObject, stack: List[Symbol], gimport: GImportIntermediateParseTree):
        # TODO: gimport only allowed in mhmodsig
        dep = Dependency(
            range=gimport.location.range,
            scope=stack[-1],
            module_name=gimport.module.text,
            module_type_hint=ModuleType.MODSIG,
            file_hint=gimport.path_to_imported_file(self.workspace.root),
            export=True)
        obj.add_dependency(dep)
        ref = Reference(dep.range, stack[-1], [dep.module_name], ReferenceType.MODSIG)
        obj.add_reference(ref)
        if gimport.repository and gimport.repository.text == util.get_repository_name(self.workspace.root, gimport.location.path):
            obj.errors.setdefault(gimport.repository.range, []).append(
                Warning(f'Redundant repository specified: "{gimport.repository.text}" is the current repository.'))

    def _compile_enter(self, obj: StexObject, symbol_stack: List[Symbol], tree: IntermediateParseTree):
        # TODO: Make sure trycatch not needed. If needed then the pop() in exit must be fixed.
        if isinstance(tree, ScopeIntermediateParseTree):
            scope = ScopeSymbol(tree.location)
            symbol_stack[-1].add_child(scope)
            symbol_stack.append(scope)
        elif isinstance(tree, ModsigIntermediateParseTree):
            self._compile_modsig(obj, symbol_stack, tree)
        elif isinstance(tree, ModnlIntermediateParseTree):
            self._compile_modnl(obj, symbol_stack, tree)
        elif isinstance(tree, ModuleIntermediateParseTree):
            self._compile_module(obj, symbol_stack, tree)
        elif isinstance(tree, TrefiIntermediateParseTree):
            self._compile_trefi(obj, symbol_stack, tree)
        elif isinstance(tree, DefiIntermediateParseTree):
            self._compile_defi(obj, symbol_stack, tree)
        elif isinstance(tree, SymIntermediateParserTree):
            self._compile_sym(obj, symbol_stack, tree)
        elif isinstance(tree, SymdefIntermediateParseTree):
            self._compile_symdef(obj, symbol_stack, tree)
        elif isinstance(tree, ImportModuleIntermediateParseTree):
            self._compile_importmodule(obj, symbol_stack, tree)
        elif isinstance(tree, GImportIntermediateParseTree):
            self._compile_gimport(obj, symbol_stack, tree)
        elif isinstance(tree, GStructureIntermediateParseTree):
            pass
        elif isinstance(tree, ViewIntermediateParseTree):
            pass
        elif isinstance(tree, ViewSigIntermediateParseTree):
            pass

    def _compile_exit(self, obj: StexObject, symbol_stack: List[Symbol], tree: IntermediateParseTree):
        if isinstance(tree, ScopeIntermediateParseTree):
            symbol_stack.pop()
        elif isinstance(tree, ModsigIntermediateParseTree):
            symbol_stack.pop()
        elif isinstance(tree, ModnlIntermediateParseTree):
            symbol_stack.pop()
        elif isinstance(tree, ModuleIntermediateParseTree):
            symbol_stack.pop()
        elif isinstance(tree, TrefiIntermediateParseTree):
            pass
        elif isinstance(tree, DefiIntermediateParseTree):
            pass
        elif isinstance(tree, SymIntermediateParserTree):
            pass
        elif isinstance(tree, SymdefIntermediateParseTree):
            pass
        elif isinstance(tree, ImportModuleIntermediateParseTree):
            pass
        elif isinstance(tree, GImportIntermediateParseTree):
            pass
        elif isinstance(tree, GStructureIntermediateParseTree):
            pass#symbol_stack.pop()
        elif isinstance(tree, ViewIntermediateParseTree):
            pass#symbol_stack.pop()
        elif isinstance(tree, ViewSigIntermediateParseTree):
            pass#symbol_stack.pop()


def _report_invalid_environments(env_name: str, lst: List[IntermediateParseTree], obj: StexObject):
    # TODO: Add invalid environments
    for invalid_environment in lst:
        obj.errors[invalid_environment.location].append(
            CompilerWarning(f'Invalid environment of type {type(invalid_environment).__name__} in {env_name}.'))
