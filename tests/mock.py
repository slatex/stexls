import tempfile
from pathlib import Path
from typing import Tuple


class MockGlossary:
    repo_name = 'git-repository'
    module_name = 'module-name'
    lang = 'en'

    def setup(self):
        self.dir = tempfile.TemporaryDirectory()
        self.root = Path(self.dir.name)
        self.new_repo('git-repo')
        self.new_module('module-name')

    def new_repo(self, name: str) -> Tuple[Path, Path]:
        """ Helper function that creates a new repository source directory.

        Args:
            name (str): Name of the repository.

        Returns:
            Path: Path to source directory and path to a general purpose file inside the source directory.
        """
        self.repo_name = name
        self.source = self.root / self.repo_name / 'source'
        self.source.mkdir(parents=True)
        self.file = self.source / 'file.tex'
        return self.source, self.file

    def new_module(self, name: str, lang: str = 'en') -> Tuple[Path, Path]:
        """ Helper function that creates a new module into the current repository.

        Args:
            name (str): Name of the module.
            lang (str, optional): Language extension of the binding.

        Returns:
            Tuple[Path, Path]: Tuple of path to module .tex and binding .tex files inside the module.
        """
        self.module_name = name
        self.lang = lang
        self.module = self.source / f'{self.module_name}.tex'
        self.binding = self.source / f'{self.module_name}.{self.lang}.tex'
        return self.module, self.binding

    def write_binding(self, content: str = '') -> Path:
        """ Surround content with mhmodnl and write to the current binding file.

        Args:
            content (str, optional): Content of the binding. Defaults to ''.

        Returns:
            Path: Path to the binding that was written to.
        """
        self.binding.write_text(rf'''
            \begin{{mhmodnl}}{{{self.module_name}}}{{{self.lang}}}
                {content}
            \end{{mhmodnl}}''')
        return self.binding

    def write_modsig(self, content: str = '') -> Path:
        """ Surround content with a modsig environment and write it to the current module file.

        Args:
            content (str, optional): Content of the modsig environment. Defaults to ''.

        Returns:
            Path: Path to the module file that was written to.
        """
        self.module.write_text(rf'''
            \begin{{modsig}}{{{self.module_name}}}
                {content}
            \end{{modsig}}
        ''')
        return self.module

    def write_text(self, content: str) -> Path:
        """ Write content to the general purpose file.

        Args:
            content (str): Content of the file.

        Returns:
            Path: Path to the general purpose file that was written to.
        """
        self.file.write_text(content)
        return self.file

    def cleanup(self):
        self.dir.cleanup()
