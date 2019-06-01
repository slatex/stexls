from __future__ import annotations

import functools
from glob import glob
import os
import multiprocessing
import re
import itertools

from . import location
from ..tokenization import TexDocument
from .file_watcher import FileWatcher


class ModuleIdentifier:
    def __init__(self, base, repository_name, module_name):
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
        assert parts[-2] == 'source'
        assert len(parts) >= 4  # smglom/repo/source/module
        return ModuleIdentifier(
            base=parts[-4],
            repository_name=parts[-3],
            module_name=parts[-1].split('.')[0],
        )


class Symbol(location.Location):
    def __init__(self, document: TexDocument, full_range: location.Range, env: str, tokens: list):
        """
        :param document: TexDocument of file e.g.: .../smglom/a/source/b.en.tex
        :param full_range: begin(\\env[oargs]{rarg1}{rarg2}), end(\\env[oargs]{rarg1}{rarg2})
        :param env: env of the symbol, e.g. here: "env"
        :param tokens: list of [oargs, rarg1, rarg2]
        """
        super().__init__(document.file, full_range)
        self.document = document
        self.env = env
        self.tokens = tokens
        self.module = ModuleIdentifier.from_file(document.file)

    @property
    def oargs(self):
        return list(itertools.takewhile(
            lambda token: token.envs[token.envs.index(self.env) + 1] == 'OArg',
            self.tokens
        ))

    @property
    def named_oargs(self):
        """
            Returns a dict of named oargs e.g.:
            given: \\env[unnamed,name1=abc,name2=def]{...}{...}
            returns: {"name1": "abc", "name2": "def"}
        """
        if len(self.oargs) == 0:
            return {}
        return dict(
            arg.split('=')
            for oarg
            in self.oargs
            for arg
            in oarg.lexeme.split(',')
            if '=' in arg)

    @property
    def named_oarg_ranges(self):
        """ Returns the ranges of the named oargs """
        expr = re.compile(r"(\w+)=([a-zA-Z0-9_\-]+)")
        return {
            match.group(1): location.Range(
                location.Position(*self.document.offset_to_position(oarg.begin + match.span(2)[0])),
                location.Position(*self.document.offset_to_position(oarg.begin + match.span(2)[1])))
            for oarg
            in self.oargs
            for match
            in expr.finditer(oarg.lexeme)
        }

    @property
    def rargs(self):
        return list(itertools.takewhile(
            lambda token: token.envs[token.envs.index(self.env) + 1] == 'RArg',
            itertools.dropwhile(lambda token: 'OArg' in token.envs, self.tokens)
        ))

    @staticmethod
    def create(document: TexDocument, pattern):
        for tokens, begin_offset, env in document.find_all(pattern, return_position=True, return_env_name=True):
            if not tokens:
                continue
            begin_position = location.Position(*document.offset_to_position(begin_offset))
            end_offset = tokens[-1].end
            end_position = location.Position(*document.offset_to_position(end_offset+1))
            full_range = location.Range(begin_position, end_position)
            yield Symbol(document, full_range, env, tokens)


class ModuleDefinition:
    pattern = re.compile(r"modsig")

    def __init__(self, symbol):
        self.symbol = symbol
        if len(symbol.rargs) != 1:
            raise Exception(f'"modsig" environment requires exactly 1 argument (found: {len(symbol.rargs)})')
        basename = os.path.basename(symbol.file).split('.')[0]
        if symbol.rargs[0].lexeme != basename.lower():
            raise Exception('"modsig" module argument and filename do not match'
                            f'({basename} vs. {symbol.rargs[0].lexeme})')

    @property
    def module_identifier(self):
        return self.symbol.module


class ModuleBinding:
    pattern = re.compile(r"mhmodnl")

    def __init__(self, symbol):
        self.symbol = symbol
        parts = symbol.file.split('.')
        if len(parts) < 3:
            raise Exception(f"Module binding missing language in filename \"{symbol.file}\"")
        self.lang = parts[-2]
        if False:
            if len(self.symbol.rargs) != 2:
                print(self.symbol.tokens)
                raise Exception(f"Module {symbol.file} binding must have exactly two arguments"
                                f"(found {len(self.symbol.rargs)})")
            if self.lang != self.symbol.rargs[-1].lexeme:
                raise Exception(f"Module {symbol.file} binding language in filename an language specified in arguments"
                                f"do not match ({self.lang} vs. {self.symbol.rargs[-1].lexeme})")

    @property
    def module_identifier(self):
        return self.symbol.module


class GimportSymbol:
    pattern = re.compile(r"gimport")

    def __init__(self, symbol):
        self.symbol = symbol

    @property
    def target_module(self):
        if len(self.symbol.oargs) == 0:
            return ModuleIdentifier(self.symbol.module.base, self.symbol.module.repository_name, self.symbol.rargs[0].lexeme)
        return ModuleIdentifier(*self.symbol.oargs[0].lexeme.split('/'), self.symbol.rargs[0].lexeme)


class SymSymbol:
    pattern = re.compile(r"sym(i+|def)")

    def __init__(self, symbol):
        self.symbol = symbol

    @property
    def expected_argument_count(self):
        return 1 if self.is_symdef else (len(re.fullmatch(SymSymbol.pattern, self.symbol.env).group(1)) if self.is_symi else None)

    @property
    def is_symi(self):
        return re.compile(r"symi+").fullmatch(self.symbol.env)

    @property
    def is_symdef(self):
        return re.compile(r"symdef").fullmatch(self.symbol.env)

    @property
    def name(self):
        if self.is_symi:
            return '-'.join([
                arg.lexeme
                for arg
                in self.symbol.rargs
            ])
        elif self.is_symdef:
            return self.symbol.named_oargs.get('name')
        else:
            raise Exception("Unreachable code: class Sym has to either be a symi or symdef")


class BindingSymbol:
    def __init__(self, symbol):
        self.symbol = symbol
        parts = symbol.file.split('.')
        if len(parts) < 3:
            raise Exception(f"Binding Symbol missing language in filename \"{symbol.file}\"")
        self.lang = parts[-2]

    @property
    def is_alt(self):
        return re.compile(r"m?am?(d|tr)efi+s?").fullmatch(self.symbol.env)

    @property
    def atokens(self):
        if self.is_alt:
            return self.symbol.rargs[0]
        return None
    
    @property
    def tokens(self):
        if self.is_alt:
            return [t for t in self.symbol.rargs[1:]]
        else:
            return [t for t in self.symbol.rargs]

    @property
    def lexemes(self):
        return [t.lexeme for t in self.tokens]


class DefiSymbol(BindingSymbol):
    pattern = re.compile(r"[ma]*def(i+)s?")

    def __init__(self, symbol):
        super().__init__(symbol)

    @property
    def expected_argument_count(self):
        return len(re.fullmatch(DefiSymbol.pattern, self.symbol.env).group(1)) + (1 if self.is_alt else 0)

    @property
    def name(self):
        name = self.symbol.named_oargs.get("name")
        if name is None:
            return '-'.join(self.lexemes)
        return name

    @property
    def symbol_ranges(self):
        """ Returns the ranges for where links to the symi should be made
            e.g.: returns ranges of sym-name, "symbol name", sym and name in
                \\adefii[name=sym-name]{symbol name}{sym}{name}
        """

        return


class TrefiSymbol(BindingSymbol):
    pattern = re.compile(r"[ma]*tref(i+)s?")

    def __init__(self, symbol):
        super().__init__(symbol)

    @property
    def expected_argument_count(self):
        return len(re.fullmatch(TrefiSymbol.pattern, self.symbol.env).group(1)) + (1 if self.is_alt else 0)

    @property
    def target_module(self):
        """ return "module" part of \\atrefi[module?symbol]{alt}{arg1}{arg2}
            or the same module as the symbol is defined in if not specified.
        """
        oargs = self.symbol.oargs
        if len(oargs) == 0:
            return self.symbol.module
        else:
            return ModuleIdentifier(
                self.symbol.module.base,
                self.symbol.module.repository_name,
                # take module from oarg or keep current module in case of e.g. \\trefi[?nary]{$n$-ary}
                oargs[0].lexeme.split('?')[0] or self.symbol.module.module_name)

    @property
    def target_symbol_name(self):
        """ returns the "symbol" part of \\atrefi[module?symbol]{alt}{arg1}{arg2}
            or "arg1-arg2" if "symbol" is not specified.
        """
        oargs = self.symbol.oargs
        if len(oargs) == 0 or '?' not in oargs[0].lexeme:
            return '-'.join(self.lexemes)
        elif len(oargs) > 0 and '?' in oargs[0].lexeme:
            return oargs[0].lexeme.split('?')[-1]

    @property
    def target_module_range(self):
        """ returns the range of where the module in oargs is located or None
            e.g.: "module" in \\trefi[module?symbol]{...}
        """
        oargs = self.symbol.oargs
        if len(oargs) == 0:
            return None
        module_parts = oargs[0].lexeme.split('?')
        if not module_parts:
            return None
        module_part = module_parts[0]
        begin = oargs[0].begin
        return location.Range(
            self.symbol.document.offset_to_position(begin),
            self.symbol.document.offset_to_position(begin+len(module_part))
        )

    @property
    def target_symbol_ranges(self):
        """ Returns the ranges of all symbols
            e.g.: in \\atrefi[module?symbol1]{symbol2}{symbol3}...
            returns ranges of symbol1, symbol2 and symbol3
        """
        ranges = []
        oargs = self.symbol.oargs
        if len(oargs) > 0 and '?' in oargs[0].lexeme:
            end = oargs[0].end
            name = oargs[0].lexeme.split('?')[-1]
            begin = end - len(name)
            ranges.append(location.Range(
                self.symbol.document.offset_to_position(begin),
                self.symbol.document.offset_to_position(end)))
        for token in itertools.chain(self.atokens, self.tokens):
            ranges.append(location.Range(
                token.begin,
                token.end))
        return ranges

class DatabaseDocument:
    def __init__(self, file: str):
        self.document = TexDocument(file)
        self.exceptions = []
        if self.document.success:
            def catcher(symbol_type_constructor):
                def wrapper(symbol):
                    try:
                        symbol = symbol_type_constructor(symbol)
                        if isinstance(symbol, (SymSymbol, DefiSymbol)):
                            if symbol.name is None:
                                raise Exception(f'Symbol {symbol.symbol.env} failed to parse arguments')
                        if False:
                            if isinstance(symbol, (TrefiSymbol, DefiSymbol,)) and len(symbol.symbol.oargs) > 1:
                                raise Exception(f"Argument count mismatch at {symbol.symbol}: "
                                                f"Expected 0 or 1, bound {len(symbol.symbol.oargs)}")
                            if (isinstance(symbol, (TrefiSymbol, DefiSymbol, SymSymbol))
                                    and len(symbol.symbol.rargs) != symbol.expected_argument_count):
                                if not isinstance(symbol, SymSymbol) or symbol.is_symi:
                                    raise Exception(f"Argument count mismatch at {symbol.symbol}: "
                                                    f"Expected {symbol.expected_argument_count},"
                                                    f"found {len(symbol.symbol.rargs)} -> {symbol.symbol.rargs}")
                        return symbol
                    except Exception as e:
                        self.exceptions.append(e)
                return wrapper
            self.syms = list(filter(None, map(catcher(SymSymbol), Symbol.create(
                                   document=self.document,
                                   pattern=SymSymbol.pattern))))
            self.gimports = list(filter(None, map(catcher(GimportSymbol), Symbol.create(
                                   document=self.document,
                                   pattern=GimportSymbol.pattern))))
            self.trefis = list(filter(None, map(catcher(TrefiSymbol), Symbol.create(
                                   document=self.document,
                                   pattern=TrefiSymbol.pattern))))
            self.defis = list(filter(None, map(catcher(DefiSymbol), Symbol.create(
                                   document=self.document,
                                   pattern=DefiSymbol.pattern))))
            modules = list(filter(None, map(catcher(ModuleDefinition), Symbol.create(
                                   document=self.document,
                                   pattern=ModuleDefinition.pattern))))
            self.module = None
            if len(modules) > 1:
                raise Exception(f"Multiple modules in {file}")
            elif len(modules) == 1:
                self.module, = modules
            bindings = list(filter(None, map(catcher(ModuleBinding), Symbol.create(
                                   document=self.document,
                                   pattern=ModuleBinding.pattern))))
            self.binding = None
            if len(bindings) > 1:
                raise Exception(f"Multiple bindings in {file}")
            elif len(bindings) == 1:
                self.binding, = bindings

    @property
    def module_identifier(self):
        if self.binding:
            return self.binding.module_identifier
        if self.module:
            return self.module.module_identifier


class Database(FileWatcher):
    def __init__(self):
        super().__init__(['.tex'])
        self._map_file_to_document = {}
        self._map_module_identifier_to_bindings = {}
        self._map_module_identifier_to_module = {}
        self._watched_directories = []
        self.failed_to_parse = {}

        self.exceptions = {}

    def module_at_position(self, file, line, column):
        doc = self._map_file_to_document.get(file)
        if doc is None:
            raise Exception("File not tracked currently")


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
                self._remove_file(file)
            except Exception as e:
                self.exceptions.setdefault(file, [])
                self.exceptions[file].append(e)

        # Parse all files in parallel or sequential
        with multiprocessing.Pool(n_jobs) as pool:
            documents = pool.map(DatabaseDocument, modified)

        for failed_document in filter(lambda doc: not doc.document.success, documents):
            self.failed_to_parse[failed_document.document.file] = failed_document.exceptions

        for document in filter(lambda document: document.document.success, documents):
            try:
                self._add_doc(document)
            except Exception as e:
                self.exceptions.setdefault(document.document.file, [])
                self.exceptions[document.document.file].append(e)

        return len(documents)

    def print_outline(self, modules=None):
        from termcolor import colored
        for modid, module in self._map_module_identifier_to_module.items():
            if modules and modid not in modules:
                continue
            print(colored('MODULE', 'yellow'), colored(modid, 'green'), module.document.file)
            print(colored('\tIMPORTS', 'blue'))
            for gimport in module.gimports:
                print('\t\t', colored(gimport.target_module, 'green'))
            print(colored('\tSYMBOLS', 'magenta'))
            for sym in module.syms:
                print('\t\t', colored(sym.name, 'grey'), sym.symbol)
            for lang, binding in self._map_module_identifier_to_bindings.get(modid, {}).items():
                print(colored("\tBINDING", 'green'), colored(lang, 'grey'), binding.document.file)
                for defi in binding.defis:
                    print(colored("\t\tDEFI", 'red'), colored(defi.name, 'grey'), defi.symbol)
                for trefi in binding.trefis:
                    print(colored("\t\tTREFI", 'blue'), colored(trefi.target_module, 'green'), colored(trefi.target_symbol_name, 'grey'), trefi.symbol)

    def _remove_file(self, file):
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

    def _add_doc(self, document):
        self._map_file_to_document[document.document.file] = document
        module = str(document.module_identifier)
        if document.binding:
            print("+BINDING", document.module_identifier, document.binding.lang, os.path.basename(document.document.file))
            self._map_module_identifier_to_bindings.setdefault(module, {})
            if document.binding.lang in self._map_module_identifier_to_bindings[module]:
                raise Exception(f'Duplicate binding for language {document.binding.lang}'
                                f'in module {module} at {document.document.file}')
            self._map_module_identifier_to_bindings[module][document.binding.lang] = document

        if document.module:
            print("+MODULE", document.module_identifier, os.path.basename(document.document.file))
            if module in self._map_module_identifier_to_module:
                raise Exception(f'Duplicate module definition of module {module} at {document.document.file}')
            self._map_module_identifier_to_module[module] = document