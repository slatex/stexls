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
import logging

log = logging.getLogger(__name__)

from stexls.vscode import DocumentUri, Position, Range, Location
from stexls.util.workspace import Workspace
from stexls.util.format import format_enumeration

from .parser import *
from .symbols import *
from .exceptions import *
from . import util

__all__ = ['Compiler', 'StexObject']

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
        """
        self.range = range
        self.scope = scope
        self.module_name = module_name
        self.module_type_hint = module_type_hint
        self.file_hint = file_hint
        self.export = export

    def __repr__(self):
        return f'[Dependency at={self.range} module={self.module_name} type={self.module_type_hint} file="{self.file_hint}" export={self.export}]'


class Reference:
    def __init__(self, range: Range): self.range = range


class SymbolReference(Reference):
    def __init__(self, range: Range, name: Iterable[str]):
        super().__init__(range)
        self.name = name

    def __repr__(self): return f'[SymbolReference "{self.name}" at {self.range}]'


class FileReference(Reference):
    def __init__(self, range: Range, file: Path):
        super().__init__(range)
        self.file = file

    def __repr__(self): return f'[FileReference "{self.file}" at {self.range}]'


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

    def format(self):
        f = f'\nFile: "{self.file}"'
        f += '\nDependencies:'
        if self.dependencies:
            for dep in self.dependencies:
                f += f'\n\t{dep}'
        else:
            f += 'n\tNo dependencies.'
        f += '\nReferences:'
        if self.references:
            for ref in self.references:
                f += f'\n\t{ref}'
        else:
            f += '\n\tNo references.'
        f += '\nErrors:'
        if self.errors:
            for r, errs in self.errors.items():
                for err in errs:
                    f += f'\n\t{r}: {err}'
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
        self.dependencies.append(dep)

    def add_reference(self, reference: Reference):
        """ Registers a reference.

        Parameters:
            reference: Information about the reference.
        """
        self.references.append(reference)


class Compiler:
    def __init__(self, root: Path, outdir: Path):
        self.root = root.expanduser().resolve().absolute()
        self.outdir = outdir.expanduser().resolve().absolute()

    def compile(self, file: Path, content: str = None):
        file = file.expanduser().resolve().absolute()
        objectfile = Compiler.get_objectfile_path(self.outdir, file)
        objectdir = objectfile.parent
        for _ in range(2): # give it two attempts to figure out whats going on
            if content is not None or not objectfile.is_file() or objectfile.lstat().st_mtime < file.lstat().st_mtime:
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
                    log.exception('Failed to write object in "%s" to "%s".', file, objectfile)
                    # ignore errors if objectfile can't be written to disk
                    # and continue as usual
                    pass
                return object
            try:
                # else load from cached
                with open(objectfile, 'rb') as fd:
                    return pickle.load(fd)
            except:
                # if loading fails, attempt to delete the cachefile
                if objectfile.is_file():
                    objectfile.unlink()
                # because this is a for loop, try again after deleting it

    def _compile_modsig(self, obj: StexObject, stack: List[Symbol], modsig: ModsigIntermediateParseTree):
        name_location = modsig.location.replace(positionOrRange=modsig.name.range)
        if obj.file.name != f'{modsig.name.text}.tex':
            obj.errors[name_location.range].append(
                CompilerWarning(f'Invalid modsig filename: Expected "{modsig.name.text}.tex"'))
        module = ModuleSymbol(
            module_type=ModuleType.MODSIG,
            location=name_location,
            name=modsig.name.text)
        stack[-1].add_child(module)
        stack.append(module)

    def _compile_modnl(self, obj: StexObject, stack: List[Symbol], modnl: ModnlIntermediateParseTree):
        if obj.file.name != f'{modnl.name.text}.{modnl.lang.text}.tex':
            obj.errors[modnl.location].append(CompilerWarning(f'Invalid modnl filename: Expected "{modnl.name.text}.{modnl.lang.text}.tex"'))
        # Add the reference from the module name to the parent module
        ref = SymbolReference(modnl.name.range, [modnl.name.text])
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
            module: ModuleSymbol = stack[-1].current_module
            if not module:
                obj.errors.setdefault(trefi.location.range, []).append(
                    CompilerWarning('Invalid drefi location: Parent module symbol not found.'))
            else:
                module.add_child(VerbSymbol(VerbType.DREF, trefi.location, trefi.name))
        if trefi.module:
            obj.add_reference(SymbolReference(trefi.module.range, [trefi.module.text]))
            obj.add_reference(SymbolReference(trefi.location.range, [trefi.module.text, trefi.name]))
        else:
            try:
                module_name: str = trefi.find_parent_module_name()
                obj.add_reference(SymbolReference(trefi.location.range, [module_name, trefi.name]))
            except:
                obj.format()
                raise
        if trefi.m:
            obj.errors.setdefault(trefi.location.range, []).append(
                DeprecationWarning('mtref environments are deprecated.'))
            has_q = trefi.target_annotation and '?' in trefi.target_annotation.text
            if not has_q:
                obj.errors.setdefault(trefi.location.range, []).append(
                    CompilerError('Invalid "mtref" environment: Target symbol must be clarified by using "?<symbol>" syntax.'))

    def _compile_defi(self, obj: StexObject, stack: List[Symbol], defi: DefiIntermediateParseTree):
        if isinstance(defi.find_parent_module_name(), ModuleIntermediateParseTree):
            symbol = VerbSymbol(VerbType.DEF, defi.location, defi.name)
            stack[-1].add_child(symbol)
        else:
            obj.add_reference(SymbolReference(defi.location.range, [defi.find_parent_module_name(), defi.name]))

    def _compile_sym(self, obj: StexObject, stack: List[Symbol], sym: SymIntermediateParserTree):
        symbol = VerbSymbol(VerbType.SYM, sym.location, sym.name, noverb=sym.noverb.is_all, noverbs=sym.noverb.langs)
        stack[-1].add_child(symbol)

    def _compile_symdef(self, obj: StexObject, stack: List[Symbol], symdef: SymdefIntermediateParseTree):
        symbol = VerbSymbol(
            VerbType.SYMDEF,
            symdef.location,
            symdef.name.text,
            noverb=symdef.noverb.is_all,
            noverbs=symdef.noverb.langs)
        stack[-1].add_child(symbol, alternative=True)

    def _compile_importmodule(self, obj: StexObject, stack: List[Symbol], importmodule: ImportModuleIntermediateParseTree):
        dep = Dependency(
            range=importmodule.location.range,
            scope=stack[-1],
            module_name=importmodule.module.text,
            module_type_hint=ModuleType.MODULE,
            file_hint=importmodule.path_to_imported_file(self.root),
            export=importmodule.export) #TODO: Is usemodule exportet?
        obj.add_dependency(dep)
        ref = SymbolReference(importmodule.location.range, [importmodule.module.text])
        obj.add_reference(ref)
        if importmodule.repos:
            obj.errors.setdefault(importmodule.repos.range, []).append(
                DeprecationWarning('Argument "repos" is deprecated and should be replaced with "mhrepos".'))
        if importmodule.mhrepos and importmodule.mhrepos.text == util.get_repository_name(self.root, obj.file):
            obj.errors.setdefault(importmodule.mhrepos.range, []).append(
                Warning(f'Redundant mhrepos key: "{importmodule.mhrepos.text}" is the current repository.'))
        if importmodule.path and importmodule.path.text == util.get_path(self.root, obj.file):
            obj.errors.setdefault(importmodule.path.range, []).append(
                Warning(f'Redundant path key: "{importmodule.path.text}" is the current path.'))
        if importmodule.dir and importmodule.dir.text == util.get_dir(self.root, obj.file).as_posix():
            obj.errors.setdefault(importmodule.location.range, []).append(
                Warning(f'Targeted dir "{importmodule.dir.text}" is the current dir.'))

    def _compile_gimport(self, obj: StexObject, stack: List[Symbol], gimport: GImportIntermediateParseTree):
        dep = Dependency(
            range=gimport.location.range,
            scope=stack[-1],
            module_name=gimport.module.text,
            module_type_hint=ModuleType.MODSIG,
            file_hint=gimport.path_to_imported_file(self.root),
            export=True)
        obj.add_dependency(dep)
        ref = SymbolReference(dep.range, [dep.module_name])
        obj.add_reference(ref)
        if gimport.repository and gimport.repository.text == util.get_repository_name(self.root, gimport.location.path):
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
            symbol_stack.pop()
        elif isinstance(tree, ViewIntermediateParseTree):
            symbol_stack.pop()
        elif isinstance(tree, ViewSigIntermediateParseTree):
            symbol_stack.pop()

    @property
    def objectfiles(self) -> Set[Path]:
        ' Return paths to all objectfiles in the output directory. '
        return set(map(Path, glob.glob((self.outdir / '*/*.stexobj').as_posix(), recursive=True)))

    @staticmethod
    def compute_objectfile_path_hash(path: Path) -> str:
        ' Computes an hash from the path to an objectfile. '
        return sha1(path.parent.as_posix().encode()).hexdigest()

    @staticmethod
    def get_objectfile_path(outdir: Path, file: Path) -> Path:
        ' Returns the path to where the objectfile should be cached. '
        return outdir / Compiler.compute_objectfile_path_hash(file) / (file.name + '.stexobj')


def _report_invalid_environments(env_name: str, lst: List[IntermediateParseTree], obj: StexObject):
    # TODO: Add invalid environments
    for invalid_environment in lst:
        obj.errors[invalid_environment.location].append(
            CompilerWarning(f'Invalid environment of type {type(invalid_environment).__name__} in {env_name}.'))
