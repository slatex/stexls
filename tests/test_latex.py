import tempfile
from pathlib import Path
from unittest import TestCase

from stexls.util.latex.parser import LatexParser
from stexls.util.latex.tokenizer import LatexTokenizer


class SetupEnvironment:
    def setUp(self):
        self.root = tempfile.TemporaryDirectory()
        root_path = Path(self.root.name)
        self.file = root_path / 'file.tex'
        with self.file.open('w+') as fd:
            fd.write(r"""
\begin{document}
    Content of document.
    \begin{nested}
        Content of nested.
        \inline_nested[arg1=value,flag]{Inline nested content.}
    \end{nested}
    \inline[inline_arg,inline=value]{$this is a nested math environment. \ignored{inside math environments are ignored}.$}
\end{document}
\begin{sequential}
    End of document inside an environment that is sequential to begin{document}.
\end{sequential}""")

    def tearDown(self) -> None:
        self.root.cleanup()


class TestLatexParser(SetupEnvironment, TestCase):
    def test_parse_file(self):
        parser = LatexParser(self.file)
        parser.parse()
        self.assertTrue(parser.parsed)
        expected_token_contents = [
            "Content of document.",
            "Content of nested.",
            "Inline nested content.",
            r"$this is a nested math environment. \ignored{inside math environments are ignored}.$",
            "End of document inside an environment that is sequential to begin",
            "document",
            "."
        ]
        self.assertListEqual(expected_token_contents,
                             list(map(lambda x: x.lexeme.strip(), parser.root.tokens)))


class TestLatexTokenizer(SetupEnvironment, TestCase):
    def test_tokenize(self):
        tokenizer = LatexTokenizer.from_file(self.file)
        expected_tokens = (
            r'''content of document . content of nested . inline nested content . '''
            r'''<math> end of document inside an environment that is sequential to begin document .'''.split()
        )
        self.assertListEqual(expected_tokens, list(
            map(lambda x: x.lexeme, tokenizer.tokens())))

    def test_environments(self):
        tokenizer = LatexTokenizer.from_file(self.file)
        expected_envs = [
            ('document',),
            ('document',),
            ('document',),
            ('document',),
            ('document', 'nested'),
            ('document', 'nested'),
            ('document', 'nested'),
            ('document', 'nested'),
            ('document', 'nested', 'inline_nested'),
            ('document', 'nested', 'inline_nested'),
            ('document', 'nested', 'inline_nested'),
            ('document', 'nested', 'inline_nested'),
            ('document', 'inline', '$'),
            ('sequential',),
            ('sequential',),
            ('sequential',),
            ('sequential',),
            ('sequential',),
            ('sequential',),
            ('sequential',),
            ('sequential',),
            ('sequential',),
            ('sequential',),
            ('sequential',),
            ('sequential',),
            ('sequential',),
        ]
        envs = list(map(lambda x: x.envs, tokenizer.tokens()))
        self.assertListEqual(expected_envs, envs)
