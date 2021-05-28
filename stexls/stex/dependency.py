from __future__ import annotations

from pathlib import Path

from .. import vscode
from . import symbols


class Dependency:
    def __init__(
            self,
            range: vscode.Range,
            scope: symbols.Symbol,
            module_name: str,
            module_type_hint: symbols.ModuleType,
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
