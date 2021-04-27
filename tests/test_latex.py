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

    def test_math_environments(self):
        self.file.write_text(r'''
        $math 1. Also ignore escaped sequences: \$$
        $$math 2$$
        \(math 3\)
        \[math 4\]
        \begin{math}math 5\end{math}
        \begin{displaymath}math 6\end{displaymath}
        \begin{align}math 7\end{align}
        \begin{flalign}math 8\end{flalign}
        \begin{flmath}math 9\end{flmath}
        \begin{equation}math 10\end{equation}
        \begin{verbatim}
            math 11. All these environments should ignore
            nested environemnts like
            \begin{document}
                this is not an environemnt!
            \end{document}
        \end{verbatim}
        \begin{lstlisting}math 12\end{lstlisting}
        ''')
        parser = LatexParser(self.file)
        parser.parse()
        self.assertTrue(parser.parsed)
        self.assertEqual(len(list(parser.root.tokens)), 12)
        self.assertEqual(next(parser.root.tokens).lexeme,
                         '$math 1. Also ignore escaped sequences: \\$$')
        for token in parser.root.tokens:
            self.assertTupleEqual(('$',), token.envs)


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
