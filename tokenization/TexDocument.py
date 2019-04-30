import collections as _collections
import TexSoup as _TexSoup
from os import path as _path
import re as _re
from .filters import TokenizerFilters

class TexDocument:
    def __init__(self, document_or_path=None, lower=False):
        """Represents a parsed tex document and its tokens with applied environments
        
        Keyword Arguments:
            document_or_path {str} -- Tex document content or path to a document (default: {None})
            lower {bool} -- If True, calls lower() on the source (default: {True})
        """
        self.lower = lower
        self._source = None
        if document_or_path is not None:
            self.parse(document_or_path)

    def offset_to_position(self, offset):
        i = 0
        offset = min(len(self.source), offset)
        for i, line in enumerate(self.source.split('\n')):
            if offset - len(line) <= 0:
                break
            offset -= len(line) + 1
        return i+1, offset+1

    def position_to_offset(self, position):
        lines = self.source.split('\n')
        lines = list(map(len, lines[:position[0]-1]))
        return sum(lines) + len(lines) + position[1]-1

    def __iter__(self):
        return iter(self.tokens if self.success else ())

    def parse(self, document_or_path):
        """Loads a document and/or parses a tex file and mapps regions to environments
        
        Arguments:
            document_or_path {str} -- Tex document as string or a path to a document
        
        Returns:
            list -- List of largest regions with same environments
        """
        self.success = False
        self.exception = None
        self._source = None
        self.file = None
        if _path.isfile(document_or_path):
            self.file = document_or_path
        else:
            self._source = document_or_path
        self.mapping, mapped_source = TexDocument.map_math_regions(self.source)
        try:
            parsed = _TexSoup.TexSoup(mapped_source)
            self.offset = 0
            self._envs = []
            self.tokens = []
            self.environments = _collections.defaultdict(list)
            self.env_begins = _collections.defaultdict(list)
            self._environment_token_stack = []
            self.onNode(parsed)
            self.tokens = [sub for token in TexDocument.fix_inner_environments(self.tokens) for sub in token.subtokens()]
            self.success = True
        except Exception as exception:
            self.exception = exception
        finally:
            if hasattr(self, '_envs'):
                del self._envs
            if hasattr(self, '_environment_token_stack'):
                del self._environment_token_stack
    
    @property
    def source(self):
        if self._source is None:
            if self.file:
                try:
                    try:
                        with open(self.file, encoding='utf-8') as file:
                                self._source = file.read()
                    except:
                        try:
                            with open(self.file, encoding='unicode') as file:
                                    self._source = file.read()
                        except:
                            raise
                except Exception as e:
                    print(f"Failed to read file {self.file}:")
                    print(e)
                    return None
            if self.lower:
                self._source = self._source.lower()
            else:
                self._source = self._source
        return self._source
    
    @property
    def parsed(self):
        return _TexSoup.TexSoup(self.source)

    def _map_token_end(self, internal_offset:int):
        """ Mapps the interal offset to the original end offset. """
        return self.mapping[internal_offset - 1][1]

    def _map_token_begin(self, internal_offset:int):
        """ Mapps the interal offset to the original begin offset. """
        return self.mapping[internal_offset][0]

    @staticmethod
    def map_math_regions(doc, repl='$?$'):
        """Creates a mapping of positions of the output text document to math regions of the input document
        
        Arguments:
            doc {str} -- Raw latex document
            repl {str} -- String to replace math with

        Returns:
            dict -- Mapping from a single position in the mapped document to the expanded range (begin, end) that the position mapps to in the original document.
                    E.g.: "A $math$ test" at pos 6 would map to (3, 7) because $math$ is replaced by "$.$" in the mapping. Therefore any character in 'math' has to be mapped to '.'.
            str -- String where all math environments are replaced with thet 'repl' string
        """

        EXPRS = list(map(lambda e: _re.compile(e, _re.DOTALL | _re.M), [
            r'(?<!\$)\$[^\$]+?\$(?!\$)',
            r'\$\$.+?\$\$',
            r'\\\[.+?\\\]',
            r'\\\(.+?\\\)',
            r'\\begin{math}.+?\\end{math}',
            r'\\begin{displaymath}.+?\\end{displaymath}',
            r'\\begin{math\*}.+?\\end{math\*}',
            r'\\begin{displaymath\*}.+?\\end{displaymath\*}',
            r'\\begin{eq.*?}.+?\\end{eq.*?}',
            # TODO: This conserves token positions, but can't be searched later
            r'\\"[aou]',
            #r'\\begin{eq.*?\*}.+?\\end{eq.*?\*}'
        ]))
        
        regions = [match.span() for matches in filter(len, map(list, [_re.finditer(e, doc) for e in EXPRS])) for match in matches]

        collisions = [
            j for s1, e1 in regions
            for j, (s2, e2) in enumerate(regions)
            if not (s2 >= e1 or e2 < s1)
            and (e1 - s1) > (e2 - s1)]

        for collision_index in sorted(collisions, reverse=True):
            del regions[collision_index]

        regions = sorted(regions, key=lambda k: k[0])
        mapping = {}
        acc = 0
        running_start = 0
        end = 0
        for start, end in regions:
            for i in range(running_start, start):
                mapping[i + acc] = (i, i + 1)
            for i in range(start, start + len(repl)):
                mapping[i + acc] = (start, end)
            acc += len(repl) - (end - start)
            running_start = end
        for i in range(end, len(doc)):
            mapping[i + acc] = (i, i + 1)
        for e in EXPRS:
            doc = _re.sub(e, repl, doc)
        return mapping, doc

    @staticmethod
    def fix_inner_environments(tokens):
        """Fixes inner environments of CMDs TexSoup fails to parse
        E.g. the tex line "\outer{a}{b\inner{c}d}{e}"
        would be parsed as the tokens "a, b, inner, c, d, e" all inside the "outer" environment
        This method fixes that to be:
        (a, [outer]), (b, [outer]), (c, [outer, inner]), (d, [outer]), (e, [outer])

        Arguments:
            tokens {list} -- List of Tokens
        
        Returns:
            [list] -- The argument but fixed
        """

        # first gather all tokens that are environments but not if they are inside math environments themselves (because I don't parse math environments)
        token_envs = [i for i, token in enumerate(tokens)
                    if token.lexeme.startswith('\\')
                    and len(token.envs) and 'RArg' in token.envs and '$' not in token.envs]

        for i in token_envs: # for all indices of tokens that are actually environments
            new_env = tokens[i].lexeme[1:] # get the environment name

            def argument_depth(token):
                """ counts the consecutive 'RArg' or 'OArg' from the end """
                argc = 0
                for e in reversed(token.envs):
                    if e != 'RArg' and e != 'OArg':
                        break
                    argc += 1
                return argc

            new_env_argc = argument_depth(tokens[i]) # get the Argument depth of this environment

            for arg in tokens[i + 1:]: # go through the tokens after the environment
                arg_argdepth = argument_depth(arg)
                if arg_argdepth <= new_env_argc:
                    break # break if a token of lower argument depth appears
                arg.envs.insert(-(arg_argdepth - new_env_argc), new_env) # insert the new environment at the correct argdepth

        for i in reversed(token_envs):
            del tokens[i] # delete the environments in reverse

        return tokens

    def visit(self, child):
        if type(child) is _TexSoup.TokenWithPosition:
            self.onToken(child)
        elif type(child) in (_TexSoup.OArg, _TexSoup.RArg):
            self.onArg(child)
        elif type(child) is _TexSoup.TexNode:
            if type(child.expr) is _TexSoup.TexCmd:
                self.onCmd(child.expr)
            elif type(child.expr) is _TexSoup.TexEnv:
                self.onEnv(child.expr)
            else:
                self.onNode(child)
        elif type(child) is _TexSoup.TexCmd:
            self.onCmd(child)
        elif type(child) is _TexSoup.TexEnv:
            self.onEnv(child)
        else:
            raise Exception("Unknown node type:" + str(type(child)))
    
    def onNode(self, node):
        for child in node:
            self.visit(child)
    
    def onToken(self, token):
        if token.startswith("%"):
            return
        begin = token.position
        end = begin + len(str(token))
        #assert(self.source[begin:end] == str(token))
        if self.offset <= begin:
            self.offset = end
            if '$' in self._envs and len(self.tokens) and self._envs == self.tokens[-1].envs:
                # extend previous math token instead of adding a new one
                self.tokens[-1].end = self._map_token_end(end)
            else:
                self.tokens.append(TokenWithEnvironments(self, self._map_token_begin(begin), self._map_token_end(end), self._envs.copy()))
    
    def onCmd(self, cmd):
        self.enter_env(str(cmd.name))
        for arg in cmd.args:
            self.onArg(arg)
        for content in cmd.contents:
            self.visit(content)
        self.exit_env(str(cmd.name), self.mapping[cmd.name.position - 1][0]) # -1 for the  slash in front
    
    def onEnv(self, env):
        self.enter_env(str(env.name))
        for arg in env.args:
            self.onArg(arg)
        for content in env.contents:
            self.visit(content)
        if hasattr(env.name, 'position'):
            self.exit_env(str(env.name), self.mapping[env.name.position-1][0])
        else:
            self.exit_env(str(env.name), env.name)

    def onArg(self, arg):
        if type(arg) is _TexSoup.OArg:
            env_name = 'OArg'
        elif type(arg) is _TexSoup.RArg:
            env_name = 'RArg'
        self.enter_env(env_name)
        for a in arg.exprs:
            self.visit(a)
        self.exit_env(env_name)

    def enter_env(self, name):
        assert type(name) == str
        self._envs.append(name)
        # remember token position before entering the env
        self._environment_token_stack.append(len(self.tokens))
    
    def exit_env(self, name, position=None):
        assert type(name) == str
        assert(self._envs[-1] == name)
        del self._envs[-1]
        # push tokens for this env
        envid = self._environment_token_stack[-1]
        del self._environment_token_stack[-1]
        self.environments[name].append(self.tokens[envid:])
        self.env_begins[name].append(position)

    def find_all(self, name, return_position=False, pattern=False, return_env_name=False):
        """Finds all distinct environments with the given name
        
        Arguments:
            name {str} -- Name of the environment to find
        
        Keyword Arguments:
            return_position {bool} -- If true, also returns the position of the environment (default: {False})
            pattern {bool} -- If set, treats name as a regex (default: {False})
            return_env_name {bool} -- Returns also the environment name
        
        Returns:
            list -- List of tokens for each of the specified environment's occurences
        """
        names = set()
        if pattern:
            names = set(filter(lambda env: _re.fullmatch(name, env), self.environments))
        else:
            names = set([name])
        if return_position:
            return [result + (name,) if return_env_name else result for name in names for result in zip(self.environments.get(name, []), self.env_begins.get(name, []))]
        else:
            return [(result, name) if return_env_name else result for name in names for result in self.environments.get(name, [])]


class TokenWithEnvironments:
    def __init__(self, document, begin:int, end:int, envs:list):
        """Represents a region with same environments inside a tex source
        
        Arguments:
            document {TexDocument} -- Source document
            begin {int} -- Region begin
            end {int} -- Region end
            envs {list} -- List of environment names that are active for this region
        """
        self.document = document
        self.begin = begin
        self.end = end
        self.envs = envs

    @property
    def lexeme(self):
        return self.document.source[self.begin:self.end]

    def subtokens(self, delimeters=TokenizerFilters.DEFAULT_DELIMETER, filter_list=TokenizerFilters.WHITESPACE_FILTER):
        """ Splits the token into smaller tokens if possible. """
        if '$' in self.envs:
            yield self
        else:
            splitter = _re.compile("([%s])" % ''.join(map(_re.escape, delimeters)))
            running_start = self.begin
            submatches = []
            for m in splitter.finditer(self.lexeme):
                begin, end = m.span()
                begin += self.begin
                end += self.begin
                if running_start < begin:
                    submatches.append((running_start, begin))
                if begin < end:
                    submatches.append((begin, end))
                running_start = end
            if running_start < self.end:
                submatches.append((running_start, self.end))
            for begin, end in submatches:
                if self.document.source[begin:end] not in filter_list:
                    yield TokenWithEnvironments(self.document, begin, end, self.envs)

    def __str__(self):
        return str(tuple(self))

    def __repr__(self):
        return str(self)

    def __iter__(self):
        yield self.lexeme
        yield self.begin
        yield self.end
        yield self.envs
    
    def __getitem__(self, i):
        """ Deprecated """
        return tuple(self)[i]
