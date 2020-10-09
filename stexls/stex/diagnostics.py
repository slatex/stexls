""" This module provides an uniform way to create and accumulate diagnostics. """
from typing import List, Iterator
from pathlib import Path
from enum import Enum
from stexls.vscode import Diagnostic, DiagnosticRelatedInformation, DiagnosticSeverity, DiagnosticTag, Location, MessageActionItem
from stexls.vscode import Location, Range
from stexls.util.format import format_enumeration
from stexls.stex.references import ReferenceType

__all__ = ['Diagnostics']

class DiagnosticCodeName(Enum):
    ' Enum for uniform diagnostic code names. '
    # TODO: Names should be a little bit more consistent
    ' Duplicate symbol '
    DUPLICATE_SYMBOL = 'duplicate-symbol-check'
    ' For exceptions raised by the parser '
    PARSER_EXCEPTION = 'parser-exception'
    ' For modules which dictate what name the file the module is defined inside should be '
    MODULE_FILE_NAME_MISMATCH = 'filename-mismatch-check'
    ' Used when an environment cant semantically be placed somewhere, where it doesnt make sense (e.g. Two \\modsigs in a single file or \\symdef not inside a \\modsig) '
    SEMANTIC_LOCATION_CHECK = 'location-check'
    ' \\mtref are deprecated '
    MTREF_DEPRECATION_CHECK = 'mtref-deprecation-check'
    ' If an mtref occurs it still must have a ?<symbol> syntax or else it cant be resolved '
    MTREF_QUESTIONMARK_CHECK = 'mtref-questionmark-check'
    ' Some envs like \\symdef allow for redefinitions, but things like noverb must still be the same. '
    INVALID_REDEFINITION = 'invalid-redefinition'
    ' the OArg "repos" is deprecated and must be replaced with "mhrepos" '
    REPOS_DEPRECATION_CHECK = 'repos-deprecation-check'
    ' Environments that take a directory path as argument should omit that path if the current file is in the specified directory. '
    IS_CURRENT_DIR_CHECK = 'is-current-dir-check'
    ' An error that should never occur, but may be thrown in the case that an import resolves to multiple modules. '
    UNIQUE_DEPENDENCY_NAME = 'unique-dependency-name-check'
    ' Used when an import to a module is made that is not exported BECAUSE it is not defined. '
    UNDEFINED_MODULE_NOT_EXPORTED = 'undefined-module-not-exported'
    ' Used when an import is cyclic '
    CYCLIC_DEPENDENCY_CHECK = 'cyclic-dependency-check'
    ' File not found '
    FILE_NOT_FOUND = 'file-not-found'
    ' Undefined symbol '
    UNDEFINED_SYMBOL = 'undefined-symbol'
    ' Used when the symbol type specified in a reference does not match the resolved symbols type '
    REFERENCE_TYPE_CHECK = 'reference-type-check'
    ' Used when attempting to import a module into the same scope twice or more times '
    REDUNDANT_IMPORT_STATEMENT_CHECK = 'redundant-import-check'


class Diagnostics:
    def __init__(self, file: Path) -> None:
        self.diagnostics: List[Diagnostic] = []

    def __iter__(self) -> Iterator[Diagnostic]:
        yield from self.diagnostics

    @staticmethod
    def _parse_severity_string(string: str) -> DiagnosticSeverity:
        string = string.lower()
        if 'hint' in string:
            return DiagnosticSeverity.Hint
        if 'info' in string:
            return DiagnosticSeverity.Information
        if 'warning' in string:
            return DiagnosticSeverity.Warning
        return DiagnosticSeverity.Error

    def module_not_found_semantic_location_check(self, range: Range, env_name: str):
        self.semantic_location_check(range, env_name, 'Parent module info not found')

    def parent_must_be_root_semantic_location_check(self, range: Range, env_name: str):
        self.semantic_location_check(range, env_name, 'Parent must be root')

    def semantic_location_check(self, range: Range, env_name: str, extra: str = None):
        if extra:
            message = f'Invalid location for {env_name}: {extra}'
        else:
            message = f'Invalid location for {env_name}'
        severity = DiagnosticSeverity.Error
        code = DiagnosticCodeName.SEMANTIC_LOCATION_CHECK.value
        diagnostic = Diagnostic(range=range, message=message, severity=severity, code=code)
        self.diagnostics.append(diagnostic)

    def is_current_dir_check(self, range: Range, dir: str):
        message = f'Already located inside directory "{dir}"'
        severity = DiagnosticSeverity.Warning
        code = DiagnosticCodeName.IS_CURRENT_DIR_CHECK.value
        tag = DiagnosticTag.Unnecessary
        diagnostic = Diagnostic(range, message, severity, code, tags=[tag])
        self.diagnostics.append(diagnostic)

    def replace_repos_with_mhrepos(self, range: Range):
        message = 'Argument "repos" is deprecated and should be replaced with "mhrepos".'
        severity = DiagnosticSeverity.Warning
        code = DiagnosticCodeName.REPOS_DEPRECATION_CHECK.value
        deprecated = DiagnosticTag.Deprecated
        diagnostic = Diagnostic(range, message, severity, code, [deprecated])
        self.diagnostics.append(diagnostic)

    def invalid_redefinition(self, range: Range, other_location: Location, info: str):
        severity = DiagnosticSeverity.Error
        code = DiagnosticCodeName.INVALID_REDEFINITION.value
        related = DiagnosticRelatedInformation(other_location, 'Previous definition')
        diagnostic = Diagnostic(range, message=info, severity=severity, code=code, relatedInformation=[related])
        self.diagnostics.append(diagnostic)

    def mtref_deprecated_check(self, range: Range):
        message = '"mtref" environments are deprecated'
        severity = DiagnosticSeverity.Warning
        code = DiagnosticCodeName.MTREF_DEPRECATION_CHECK.value
        diagnostic = Diagnostic(range, message, severity=severity, code=code, tags=[DiagnosticTag.Deprecated])
        self.diagnostics.append(diagnostic)

    def mtref_questionmark_syntax_check(self, range: Range):
        message = 'Invalid "mtref" environment: Target symbol must be clarified by using "?<symbol>" syntax.'
        severity = DiagnosticSeverity.Error
        code = DiagnosticCodeName.MTREF_QUESTIONMARK_CHECK.value
        diagnostic = Diagnostic(range, message, severity=severity, code=code)
        self.diagnostics.append(diagnostic)

    def file_name_mismatch(self, range: Range, expected_name: str, actual_name: str):
        message = f'Expected the this file name "{expected_name}", but found "{actual_name}"'
        severity = DiagnosticSeverity.Warning
        code = DiagnosticCodeName.MODULE_FILE_NAME_MISMATCH.value
        diagnostic = Diagnostic(range=range, message=message, severity=severity, code=code)
        self.diagnostics.append(diagnostic)

    def duplicate_symbol_definition(self, range: Range, symbol_name: str, previous_def: Location):
        message = f'Symbol "{symbol_name}" previously defined at "{previous_def}"'
        severity = DiagnosticSeverity.Error
        code = DiagnosticCodeName.DUPLICATE_SYMBOL.value
        diagnostic = Diagnostic(range=range, message=message, severity=severity, code=code)
        self.diagnostics.append(diagnostic)

    def parser_exception(self, range: Range, exception: Exception):
        message = str(exception)
        severity = Diagnostics._parse_severity_string(type(exception).__name__)
        code = DiagnosticCodeName.PARSER_EXCEPTION.value
        diag = Diagnostic(range, message, severity, code)
        self.diagnostics.append(diag)

    def exception(self, range: Range, exception: Exception, severity: DiagnosticSeverity = None):
        message = str(exception)
        severity = severity or Diagnostics._parse_severity_string(type(exception).__name__)
        code = DiagnosticCodeName.GENERIC_EXCEPTION.value
        diagnostic = Diagnostic(range, message, severity, code)
        self.diagnostics.append(diagnostic)

    def unable_to_link_with_non_unique_module(self, range: Range, module_name: str, file: Path):
        message = f'Module "{module_name}" not unique in "{file}"'
        severity = DiagnosticSeverity.Error
        code = DiagnosticCodeName.UNIQUE_DEPENDENCY_NAME.value
        diagnostic = Diagnostic(range, message, severity, code)
        self.diagnostics.append(diagnostic)

    def undefined_symbol(self, range: Range, symbol_name: str, symbol_type: str = None, suggestions: List[str] = None):
        if symbol_type:
            message = f'Undefined symbol "{symbol_name}" of type {symbol_type}'
        else:
            message = f'Undefined symbol "{symbol_name}"'
        if suggestions:
            message += ': Did you mean ' + format_enumeration(suggestions, last='or') + '?'
        severity = DiagnosticSeverity.Error
        code = DiagnosticCodeName.UNDEFINED_SYMBOL.value
        diagnostic = Diagnostic(range, message, severity, code)
        self.diagnostics.append(diagnostic)

    def undefined_module_not_exported_by_file(self, range: Range, module_name: str, file: Path):
        message = f'Undefined module "{module_name}" symbol not exported from file "{file}"'
        severity = DiagnosticSeverity.Error
        code = DiagnosticCodeName.UNDEFINED_MODULE_NOT_EXPORTED.value
        diagnostic = Diagnostic(range, message, severity, code)
        self.diagnostics.append(diagnostic)

    def attempt_access_private_symbol(self, range: Range, symbol_name: str):
        message = f'Accessed symbol "{symbol_name}" is marked as private'
        severity = DiagnosticSeverity.Error
        code = DiagnosticCodeName.SYMBOL_ACCESS_CHECK.value
        diagnostic = Diagnostic(range, message, severity, code)
        self.diagnostics.append(diagnostic)

    def cyclic_dependency(self, range: Range, module_name: str, location_of_cyclic_import: Location):
        message = f'Cyclic dependency create at import of "{module_name}"'
        severity = DiagnosticSeverity.Error
        code = DiagnosticCodeName.CYCLIC_DEPENDENCY_CHECK.value
        related = DiagnosticRelatedInformation(location_of_cyclic_import, "Imported at")
        diagnostic = Diagnostic(range, message, severity, code, relatedInformation=[related])
        self.diagnostics.append(diagnostic)

    def file_not_found(self, range: Range, file: Path):
        message = f'File not found: "{file}"'
        severity = DiagnosticSeverity.Error
        code = DiagnosticCodeName.FILE_NOT_FOUND.value
        diagnostic = Diagnostic(range, message, severity, code)
        self.diagnostics.append(diagnostic)

    def referenced_symbol_type_check(self, range: Range, expected: ReferenceType, actual: ReferenceType):
        message = f'Expected symbol type is "{expected.format_enum()}" but the resolved symbol is of type "{actual.format_enum()}"'
        severity = DiagnosticSeverity.Error
        code = DiagnosticCodeName.REFERENCE_TYPE_CHECK.value
        diagnostic = Diagnostic(range, message, severity, code)
        self.diagnostics.append(diagnostic)

    def symbol_is_noverb_check(self, range: Range, symbol_name: str, lang: str = None):
        if lang:
            message = f'Symbol "{symbol_name}" is marked as noverb for the language "{lang}"'
        else:
            message = f'Symbol "{symbol_name}" is marked as noverb'
        severity = DiagnosticSeverity.Warning
        code = DiagnosticCodeName.NOVERB_CHECK.value
        diagnostic = Diagnostic(range, message, severity, code)
        self.diagnostics.append(diagnostic)

    def redundant_import_check(self, range: Range, module_name: str, previously_at: Location):
        message = f'Redundant import of module "{module_name}"'
        severity = DiagnosticSeverity.Warning
        code = DiagnosticCodeName.REDUNDANT_IMPORT_STATEMENT_CHECK.value
        related = DiagnosticRelatedInformation(previously_at, 'Previously located here')
        tag = DiagnosticTag.Unnecessary
        diagnostic = Diagnostic(range, message, severity, code, tags=[tag], relatedInformation=[related])
        self.diagnostics.append(diagnostic)
