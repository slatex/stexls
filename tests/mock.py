import tempfile
from pathlib import Path


class MockGlossary:
    repo_name = 'git-repository'
    module_name = 'module-name'
    lang = 'en'

    def setup(self):
        self.dir = tempfile.TemporaryDirectory()
        self.root = Path(self.dir.name)
        self.source = self.root / self.repo_name / 'source'
        self.source.mkdir(parents=True)
        self.module = self.source / f'{self.module_name}.tex'
        self.binding = self.source / f'{self.module_name}.{self.lang}.tex'
        self.file = self.source / 'file.tex'

    def write_binding(self, content: str = '') -> Path:
        self.binding.write_text(rf'''
            \begin{{mhmodnl}}{{{self.module_name}}}{{{self.lang}}}
                {content}
            \end{{mhmodnl}}''')
        return self.binding

    def write_modsig(self, content: str = '') -> Path:
        self.module.write_text(rf'''
            \begin{{modsig}}{{{self.module_name}}}
                {content}
            \end{{modsig}}
        ''')
        return self.module

    def write_text(self, content: str) -> Path:
        self.file.write_text(content)
        return self.file

    def cleanup(self):
        self.dir.cleanup()
