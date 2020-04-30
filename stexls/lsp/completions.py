from typing import *
import re
import logging
from pathlib import Path
from stexls.stex import Linker
from stexls.stex.compiler import *
from stexls.stex.symbols import *
from stexls.util.vscode import *

__all__ = ['CompletionEngine']

log = logging.getLogger(__name__)

_regex_gimport_repo = re.compile(r'\\g(use|import)\*?\[(?P<repository>[^\]]*)$')
_regex_gimport_module = re.compile(r'\\g(use|import)\*?(\[(?P<repository>.*)\])?\{(?P<module>[^\}]*)$')
_regex_named_values = re.compile(r'(?P<name>\w+)=(?P<value>[^,\]]*)') # extracts all named arguments with their values
_regex_unnamed_arg = re.compile(r'\\(?P<env>\w+)\*?[^\]]*[\[,](?P<arg>[^\],=]*)$') # matches \\<env>[<arg> or \\<env>[a=b,<arg>
_regex_named_arg = re.compile(r'\\(?P<env>\w+)\*?[^\]]*[\[,](?P<arg>\w+)=(?P<value>[^\],]*)$') # matches \\<env>*[aihaih,<arg>=<value>
_regex_rarg = re.compile(r'\\(?P<env>\w+)\*?(\[[^\]]*\])?{(?P<value>[^}]*)$')
_regex_env_importmodule = re.compile(r'(use|import)(?P<mh>mh)?module')
_regex_env_trefi = re.compile(r'(?P<flags>[ma]*)(?P<type>t|T|d|D)ref(?P<argcount>[ivx]+)s?')
_regex_env_defi = re.compile(r'[ma]*(d|D)ef(?P<argcount>[ivx]+)s?')
_regex_env_symi = re.compile(r'sym(?P<argcount>[ivx]+)s?')

class CompletionEngine:
    """ Helper class for compltion item creation.

    Adapts a linker for completion item creation.
    """
    def __init__(self, linker: Linker):
        self.linker = linker

    def completion(self, file: Path, lines: List[str], position: Position) -> List[CompletionItem]:
        ' Only method that should be used by the user. Creates a list of completion items for a file, given the position and the buffered lines in that file. '
        log.debug('Completion for file: %s at %s', file, position.format())
        try:
            obj: StexObject = next(self.linker.relevant_objects(file, position.line, position.character, unlinked=True), None)
            link: StexObject = next(self.linker.relevant_objects(file, position.line, position.character, unlinked=False), None)
            if not obj or not link:
                return []
            if lines is None:
                lines = file.read_text().split('\n')
            line = lines[position.line]
            context = line[:position.character]
        except:
            log.exception('Failed to obtain completion context.')
            return []
        log.debug('Completion line: %s', line)
        log.debug('Completion context: %s', context)
        def wrapper():
            yield from self.complete_gimport(obj, context, position)
            yield from self.complete_importmodule(obj, line, context, position)
            yield from self.complete_symi(obj, context, position)
            yield from self.complete_symdef(obj, context, position)
            yield from self.complete_trefi(obj, link, context, position)
            yield from self.complete_defi(obj, link, context, position)
        return list(wrapper())

    def get_gimport_repositories(self) -> Set[str]:
        ' Get all repository identifiers which contain with MODSIG defined modules. '
        return set(module.get_repository_identifier(self.linker.root) for module in self.linker.get_all_modules(DefinitionType.MODSIG))

    def get_gimport_modules(self, object: StexObject, repo: Optional[str]) -> Set[str]:
        ' Get all module names which are importable in gimport/use statements. If repo is not given, the repository in which <object> is contained in will be used. '
        return set(
            module.identifier.identifier
            for module in self.linker.get_all_modules(DefinitionType.MODSIG)
            if (repo and repo == module.get_repository_identifier(self.linker.root))
            or (not repo and module.location.path.parent == object.path.parent))

    def complete_gimport(self, object: StexObject, context: str, position: Position) -> List[CompletionItem]:
        for match in _regex_gimport_module.finditer(context):
            repo = match.group('repository')
            fragment = match.group('module')
            return [
                self._make_completion_item(fragment, module, CompletionItemKind.Module, position)
                for module in self.get_gimport_modules(object, repo)
                if module.startswith(fragment)
            ]
        for match in _regex_gimport_repo.finditer(context):
            fragment = match.group('repository')
            return [
                self._make_completion_item(fragment, repository, CompletionItemKind.Folder, position)
                for repository in self.get_gimport_repositories()
                if repository.startswith(fragment)
            ]
        return []
    
    def get_named_arguments(self, line: str) -> Dict[str, str]:
        return {
            match.group('name'): match.group('value')
            for match in _regex_named_values.finditer(line)
        }

    def get_mhrepos(self, object: StexObject) -> Set[str]:
        ' Get mhrepo identifier of all with MODULE defined modules '
        return set(module.get_repository_identifier(self.linker.root) for module in self.linker.get_all_modules(DefinitionType.MODULE))

    def get_paths(self, object: StexObject, mhrepos: Optional[str] = None) -> Set[str]:
        ' Gets importmodule path= arguments of all reachable modules realtive to the given object. If mhrepos is None then all modules of the same directory will be considered. '
        return set(
            module.get_path(self.linker.root).as_posix()
            for module in self.linker.get_all_modules(DefinitionType.MODULE)
            if (mhrepos and module.get_repository_identifier(self.linker.root) == mhrepos)
            or (not mhrepos and module.location.path.parent == object.path.parent))

    def get_dirs(self, object: StexObject, mhrepos: Optional[str] = None) -> Set[str]:
        ' Gets importmodule dir= arguments of all reachable modules realtive to the given object. If mhrepos is None then all modules of the same directory will be considered. '
        return set(Path(path).parent.as_posix() for path in self.get_paths(object, mhrepos))

    def complete_importmodule(self, object: StexObject, line: str, context: str, position: Position) -> List[CompletionItem]:
        for match in _regex_unnamed_arg.finditer(context):
            if not _regex_env_importmodule.fullmatch(match.group('env')):
                continue
            fragment = match.group('arg')
            choices = ('mhrepos', 'dir', 'path', 'load')
            return self._completions_from_choices(fragment, choices, CompletionItemKind.Keyword, position)
        for match in _regex_named_arg.finditer(context):
            if not _regex_env_importmodule.fullmatch(match.group('env')):
                continue
            named = self.get_named_arguments(line)
            arg = match.group('arg')
            fragment = match.group('value')
            if arg in ('mhrepos', 'repos'):
                return [
                    self._make_completion_item(fragment, repo, CompletionItemKind.Folder, position)
                    for repo in self.get_mhrepos(object)
                    if repo.startswith(fragment)
                ]
            elif arg in ('dir', 'path'):
                mhrepos = named.get('mhrepos', named.get('repos'))
                if arg == 'dir':
                    return [
                        self._make_completion_item(fragment, dir, CompletionItemKind.Folder, position)
                        for dir in self.get_dirs(object, mhrepos)
                        if dir.startswith(fragment)
                    ]
                return [
                    self._make_completion_item(fragment, path, CompletionItemKind.File, position)
                    for path in self.get_paths(object, mhrepos)
                    if path.startswith(fragment)
                ]
            elif arg == 'load':
                return [
                    self._make_completion_item(fragment, module.location.path.as_posix(), CompletionItemKind.File, position)
                    for module in self.linker.get_all_modules(DefinitionType.MODULE)
                    if module.location.path.as_posix().startswith(fragment)
                ]
        for match in _regex_rarg.finditer(context):
            if not _regex_env_importmodule.fullmatch(match.group('env')):
                continue
            fragment = match.group('value')
            named = self.get_named_arguments(line)
            for current_module in object.symbol_table.get(object.module, []):
                current_module: Symbol # simply extract the last module symbol, ignore the rest (no others should exist anyway)
            mhrepos = named.get('mhrepos', named.get('repos'))
            if not mhrepos and current_module:
                mhrepos = current_module.get_repository_identifier(self.linker.root)
            dir = named.get('dir')
            path = named.get('path')
            load = named.get('load')
            if not (dir or path or load) and current_module:
                path = current_module.get_path(self.linker.root).as_posix()
            return [
                self._make_completion_item(fragment, module.identifier.identifier, CompletionItemKind.Module, position)
                for module in self.linker.get_all_modules(DefinitionType.MODULE)
                if module.identifier.identifier.startswith(fragment)
                and (not mhrepos or mhrepos == module.get_repository_identifier(self.linker.root))
                and (not dir or dir == module.get_path(self.linker.root).parent.as_posix())
                and (not path or path == module.get_path(self.linker.root).as_posix())
                and (not load or self.linker.root / load == module.location.path.parent / module.location.path.stem)
            ]
        return []

    def complete_symi(self, object: StexObject, context: str, position: Position) -> List[CompletionItem]:
        for match in _regex_unnamed_arg.finditer(context):
            if not _regex_env_symi.fullmatch(match.group('env')):
                continue
            fragment = match.group('arg')
            choices = ('align=', 'gfc=', 'noverb', 'noalign')
            return self._completions_from_choices(fragment, choices, CompletionItemKind.Keyword, position)
        for match in _regex_named_arg.finditer(context):
            if not _regex_env_symi.fullmatch(match.group('env')):
                continue
            arg = match.group('arg')
            fragment = match.group('value')
            # no named completions for symi
        return []

    def complete_symdef(self, object: StexObject, context: str, position: Position) -> List[CompletionItem]:
        for match in _regex_unnamed_arg.finditer(context):
            if match.group('env') != 'symdef':
                continue
            fragment = match.group('arg')
            choices = ('name', 'gfc=', 'assocarg=', 'bvars=', 'bargs=', 'noverb')
            return self._completions_from_choices(fragment, choices, CompletionItemKind.Keyword, position)
        for match in _regex_named_arg.finditer(context):
            if match.group('env') != 'symdef':
                continue
            arg = match.group('arg')
            if arg != 'name':
                continue
            fragment = match.group('value')
            choices = [
                symbol.identifier.identifier
                for id, symbols in object.symbol_table.items()
                if id.symbol_type == SymbolType.SYMBOL
                and id.identifier.startswith(fragment)
                and any(symbol.definition_type == DefinitionType.SYMDEF for symbol in symbols if isinstance(symbol, VerbSymbol))
                for symbol in symbols[:1]
            ]
            return self._completions_from_choices(fragment, choices, CompletionItemKind.Field, position)
        for match in _regex_rarg.finditer(context):
            if match.group('env') != 'symdef':
                continue
            fragment = match.group('value')
            choices = set(
                symbol.identifier.identifier
                for id, symbols in object.symbol_table.items()
                if id.symbol_type == SymbolType.SYMBOL
                and id.identifier.startswith(fragment)
                and any(symbol.definition_type == DefinitionType.SYMDEF for symbol in symbols if isinstance(symbol, VerbSymbol))
                for symbol in symbols[:1])
            return self._completions_from_choices(fragment, choices, CompletionItemKind.Field, position)
        return []

    def complete_trefi(self, object: StexObject, link: StexObject, context: str, position: Position) -> List[CompletionItem]:
        for match in _regex_unnamed_arg.finditer(context):
            if not _regex_env_trefi.fullmatch(match.group('env')):
                continue
            fragment = match.group('arg')
            if '?' in fragment:
                # complete module?symbol
                kind = CompletionItemKind.Field
                target_module = fragment.split('?')[0] or object.scope_identifier.identifier # default to scope of object
                choices = (
                    symbol.identifier.identifier
                    for id, symbols in link.symbol_table.items()
                    if id.symbol_type == SymbolType.SYMBOL
                    for symbol in symbols
                    if symbol.parent.identifier == target_module
                    and (not isinstance(symbol, VerbSymbol) or not symbol.noverb)
                )
                fragment = fragment.split('?')[-1]
            else:
                # complete module
                kind = CompletionItemKind.Module
                choices = (
                    id.identifier
                    for id in link.symbol_table
                    if id.symbol_type == SymbolType.MODULE
                )
            return self._completions_from_choices(fragment, choices, kind=kind, position=position)
        for match in _regex_named_arg.finditer(context):
            if not _regex_env_trefi.fullmatch(match.group('env')):
                continue
            # trefi does not have named arguments
        for match in _regex_rarg.finditer(context):
            if not _regex_env_trefi.fullmatch(match.group('env')):
                continue
            # TODO: Complete the literal symbol tokens
        return []

    def complete_defi(self, object: StexObject, link: StexObject, context: str, position: Position) -> List[CompletionItem]:
        for match in _regex_unnamed_arg.finditer(context):
            if not _regex_env_defi.fullmatch(match.group('env')):
                continue
            fragment = match.group('arg')
            return self._completions_from_choices(fragment, ('name',), CompletionItemKind.Keyword, position)
        for match in _regex_named_arg.finditer(context):
            if not _regex_env_defi.fullmatch(match.group('env')):
                continue
            fragment = match.group('value')
            scope = object.scope_identifier
            if match.group('arg') != 'name':
                continue
            choices = set(
                symbol.identifier.identifier
                for id, symbols in link.symbol_table.items()
                if id.symbol_type == SymbolType.SYMBOL
                for symbol in symbols
                if symbol.parent == scope)
            return self._completions_from_choices(fragment, choices, CompletionItemKind.Unit, position)
        return []

    def _completions_from_choices(self, fragment: str, choices: Iterable[str], kind: CompletionItemKind, position: Position) -> List[CompletionItem]:
        return [
            self._make_completion_item(fragment, choice, kind, position)
            for choice in choices
            if choice.startswith(fragment)
        ]

    def _make_completion_item(self, old_text: str, new_text: str, kind: CompletionItemKind, position: Position):
        assert new_text.startswith(old_text)
        range = Range(position.translate(characters=-len(old_text)), position)
        return CompletionItem(new_text, kind=kind, textEdit=TextEdit(range, new_text))
