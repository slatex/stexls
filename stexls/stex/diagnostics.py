""" This module provides an uniform way to create and accumulate diagnostics. """
from enum import Enum
from pathlib import Path
from typing import Dict, Iterator, List, Set

import numpy as np

from .. import vscode
from ..util.format import format_enumeration
from ..vscode import (Diagnostic, DiagnosticRelatedInformation,
                      DiagnosticSeverity, DiagnosticTag)
from .reference_type import ReferenceType

__all__ = ['Diagnostics']


class DiagnosticCodeName(Enum):
    ' Enum for uniform diagnostic code names. '
    # TODO: Names should be a little bit more consistent
    ' An unclassified exception occurred '
    GENERIC_EXCEPTION = 'generic-exception'
    ' The referenced module is not specified and cannot be inferred because the macro (trefi, anything else?) is used outside of any module '
    CANT_INFER_REF_MODULE_OUTSIDE_MODULE = 'cannot-infer-referenced-module-outside-module'
    ' Duplicate symbol '
    DUPLICATE_SYMBOL = 'duplicate-symbol-check'
    ' For exceptions raised by the parser '
    PARSER_EXCEPTION = 'parser-exception'
    ' For modules which dictate what name the file the module is defined inside should be '
    MODULE_FILE_NAME_MISMATCH = 'filename-mismatch-check'
    ' Used when an environment cant semantically be placed somewhere,'
    ' where it doesnt make sense (e.g. Two \\modsigs in a single file or \\symdef not inside a \\modsig) '
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
    ' Generic tag hint created by the trefier model '
    TREFIER_TAG_HINT = 'generic-trefier-tag-hint'
    ' Used when referencing a symdef tagged with noverb '
    REFERENCE_TO_NOVERB_CHECK = 'referenced-noverb-symbol'
    ' Used when something when access modifier prevents access '
    SYMBOL_ACCESS_MODIFIER_CHECK = 'access-modifier-check'


class Diagnostics:
    def __init__(self) -> None:
        self.diagnostics: List[Diagnostic] = []

    def copy(self) -> 'Diagnostics':
        ' Creates a copy of this object. '
        cpy = Diagnostics()
        cpy.diagnostics.extend(self.diagnostics)
        return cpy

    def __iter__(self) -> Iterator[Diagnostic]:
        ' Iterates through added diagnostics. '
        yield from self.diagnostics

    def trefier_tag(self, range: vscode.Range, text: str, label: np.ndarray):
        ' Create a simple diagnostic for a trefier tag. '
        message = f'Label for "{text}": {np.round(label, 2)}'
        severity = DiagnosticSeverity.Information
        code = DiagnosticCodeName.TREFIER_TAG_HINT.name
        # TODO: Diagnostics have a "related information" field, allowing them to display references to possible defis.
        # TODO: Extend the @Diagnostics class to a quick fix provider for the client, that provides quick fixes, that
        # TODO: ... automatically format these hints into defis or trefis.
        # TODO: The format operation needs information about the ranges of each token that needs to be included,
        # TODO: not just one range (which is what is currently available).
        # TODO: Example Text: "This is a prime number." would need the tags for "prime" and "number",
        # TODO: Then GROUPING needs to be done with respect to the label and location,
        # TODO: grouping "prime" and "number" into one "possible defi or trefi" unit, because they have the same label
        # TODO: and are located next to each other. You can use @itertools.groupby for this.
        # TODO: This unit is then inspected by the linter which decides using @difflib.get_close_matches and the index
        # TODO: of defined symbols which defi is being referenced.
        # TODO: Then we can create a diagnostic with the combined range of "prime" and "number", with related information
        # TODO: to the location of where \symii{prime}{number} is defined. Also a quick fix that does the follwoing edits
        # TODO: is created: "This is a prime number" -> "This is a \trefii[primenumber]{prime}{number}"
        diagnostic = Diagnostic(range, message=message,
                                severity=severity, code=code)
        self.diagnostics.append(diagnostic)

    def cant_infer_ref_module_outside_module(self, range: vscode.Range):
        severity = DiagnosticSeverity.Error
        code = DiagnosticCodeName.CANT_INFER_REF_MODULE_OUTSIDE_MODULE.value
        message = 'Cannot infer what module is referenced outside of any module'
        diagnostic = Diagnostic(
            range=range, message=message, severity=severity, code=code)
        self.diagnostics.append(diagnostic)

    def module_not_found_semantic_location_check(self, range: vscode.Range, env_name: str):
        ' Used when an environment is used at locations where a module can\'t be deduced. E.g. outside of modsig or module environments. '
        self.semantic_location_check(
            range, env_name, 'Parent module info not found')

    def parent_must_be_root_semantic_location_check(self, range: vscode.Range, env_name: str):
        ' Used when the parent of an environment is something different than root. '
        self.semantic_location_check(range, env_name, 'Parent must be root')

    def semantic_location_check(self, range: vscode.Range, env_name: str, extra: str = None):
        ' Generic semantic location check failed message: Use @extra to give more information to why the location is invalid. '
        if extra:
            message = f'Invalid location for {env_name}: {extra}'
        else:
            message = f'Invalid location for {env_name}'
        severity = DiagnosticSeverity.Error
        code = DiagnosticCodeName.SEMANTIC_LOCATION_CHECK.value
        diagnostic = Diagnostic(
            range=range, message=message, severity=severity, code=code)
        self.diagnostics.append(diagnostic)

    def is_current_dir_check(self, range: vscode.Range, dir: str):
        ' Used when environments can specify paths and the specified path is the same as the default path -> Path can be removed hint. '
        message = f'Already located inside directory "{dir}"'
        severity = DiagnosticSeverity.Warning
        code = DiagnosticCodeName.IS_CURRENT_DIR_CHECK.value
        tag = DiagnosticTag.Unnecessary
        diagnostic = Diagnostic(range, message, severity, code, tags=[tag])
        self.diagnostics.append(diagnostic)

    def replace_repos_with_mhrepos(self, range: vscode.Range):
        ' Used when the deprecated "repos=" optional argument is used. '
        message = 'Argument "repos" is deprecated and should be replaced with "mhrepos".'
        severity = DiagnosticSeverity.Warning
        code = DiagnosticCodeName.REPOS_DEPRECATION_CHECK.value
        deprecated = DiagnosticTag.Deprecated
        diagnostic = Diagnostic(
            range=range,
            message=message,
            severity=severity,
            code=code,
            tags=[deprecated]
        )
        self.diagnostics.append(diagnostic)

    def invalid_redefinition(self, range: vscode.Range, other_location: vscode.Location, info: str):
        ''' Used when redefinitions are allowed (symdef), but the redefeined symbol\'s signature is incompatible (noverb tags different)

        Parameters:
            range: vscode.Range of the causing symbol
            other_location: vscode.Location of the symbol with a different signature
            info: Information about the signature difference. Just some message string.
        '''
        severity = DiagnosticSeverity.Error
        code = DiagnosticCodeName.INVALID_REDEFINITION.value
        related = DiagnosticRelatedInformation(
            other_location, 'Previous definition')
        diagnostic = Diagnostic(
            range, message=info, severity=severity, code=code, relatedInformation=[related])
        self.diagnostics.append(diagnostic)

    def mtref_deprecated_check(self, range: vscode.Range):
        ' Used when deprecated "mtref" environment used. '
        message = '"mtref" environments are deprecated'
        severity = DiagnosticSeverity.Warning
        code = DiagnosticCodeName.MTREF_DEPRECATION_CHECK.value
        diagnostic = Diagnostic(range, message, severity=severity, code=code, tags=[
                                DiagnosticTag.Deprecated])
        self.diagnostics.append(diagnostic)

    def mtref_questionmark_syntax_check(self, range: vscode.Range):
        ' If a "mtref" is used, it must use the questionmark syntax. '
        message = 'Invalid "mtref" environment: Target symbol must be clarified by using "?<symbol>" syntax.'
        severity = DiagnosticSeverity.Error
        code = DiagnosticCodeName.MTREF_QUESTIONMARK_CHECK.value
        diagnostic = Diagnostic(range, message, severity=severity, code=code)
        self.diagnostics.append(diagnostic)

    def file_name_mismatch(self, range: vscode.Range, expected_name: str, actual_name: str):
        ' Used when an environment that has authority over the filename (e.g. gmodule) mismatches the actual filename. '
        message = f'Expected the this file name "{expected_name}", but found "{actual_name}"'
        severity = DiagnosticSeverity.Warning
        code = DiagnosticCodeName.MODULE_FILE_NAME_MISMATCH.value
        diagnostic = Diagnostic(
            range=range, message=message, severity=severity, code=code)
        self.diagnostics.append(diagnostic)

    def duplicate_symbol_definition(self, range: vscode.Range, symbol_name: str, previous_def: vscode.Location):
        ' Used when duplicate symbol definitions are not allowed. '
        message = f'Duplicate definition of symbol: "{symbol_name}"'
        severity = DiagnosticSeverity.Error
        code = DiagnosticCodeName.DUPLICATE_SYMBOL.value
        related = DiagnosticRelatedInformation(
            previous_def, message=f'Previous definition of "{symbol_name}"')
        diagnostic = Diagnostic(range=range, message=message,
                                severity=severity, code=code, relatedInformation=[related])
        self.diagnostics.append(diagnostic)

    def parser_exception(self, range: vscode.Range, exception: Exception):
        ' Used for all errors caught during parsing. '
        message = str(exception)
        severity = DiagnosticSeverity.from_string(type(exception).__name__)
        code = DiagnosticCodeName.PARSER_EXCEPTION.value
        diag = Diagnostic(range, message, severity, code)
        self.diagnostics.append(diag)

    def exception(self, range: vscode.Range, exception: Exception, severity: DiagnosticSeverity = None):
        ' Generic exception occured. '
        message = str(exception)
        severity = severity or DiagnosticSeverity.from_string(
            type(exception).__name__)
        code = DiagnosticCodeName.GENERIC_EXCEPTION.value
        diagnostic = Diagnostic(range, message, severity, code)
        self.diagnostics.append(diagnostic)

    def unable_to_link_with_non_unique_module(self, range: vscode.Range, module_name: str, file: Path):
        ' Error that should be impossible, but raised when a module is defined multiple times and some module attempts to import it. '
        message = f'Module "{module_name}" not unique in "{file}"'
        severity = DiagnosticSeverity.Error
        code = DiagnosticCodeName.UNIQUE_DEPENDENCY_NAME.value
        diagnostic = Diagnostic(range, message, severity, code)
        self.diagnostics.append(diagnostic)

    def undefined_symbol(
            self,
            range: vscode.Range,
            symbol_name: str,
            reference_type: ReferenceType = None,
            similar_symbols: Dict[str, Set[vscode.Location]] = None):
        ' Generic undefined symbol encountered error. '
        if reference_type:
            message = f'Undefined symbol "{symbol_name}" of type {reference_type.format_enum()}'
        else:
            message = f'Undefined symbol "{symbol_name}"'
        if similar_symbols:
            message += ': Did you mean ' + \
                format_enumeration(similar_symbols, last='or') + '?'
        severity = DiagnosticSeverity.Error
        code = DiagnosticCodeName.UNDEFINED_SYMBOL.value
        related_information = [
            DiagnosticRelatedInformation(location, f'Related symbol: {name}')
            for name, locations in (similar_symbols or {}).items()
            for location in locations
        ]
        diagnostic = Diagnostic(range, message, severity,
                                code, relatedInformation=related_information)
        self.diagnostics.append(diagnostic)

    def undefined_module_not_exported_by_file(self, range: vscode.Range, module_name: str, file: Path):
        ' Used when a module attempts to import a module that is not exported because it is not defined in the first place. '
        message = f'Undefined module "{module_name}" symbol not exported from file: "{file}"'
        severity = DiagnosticSeverity.Error
        code = DiagnosticCodeName.UNDEFINED_MODULE_NOT_EXPORTED.value
        diagnostic = Diagnostic(range, message, severity, code)
        self.diagnostics.append(diagnostic)

    def attempt_access_private_symbol(self, range: vscode.Range, symbol_name: str):
        ' Private symbol accessed. '
        message = f'Accessed symbol "{symbol_name}" is marked as private'
        severity = DiagnosticSeverity.Error
        code = DiagnosticCodeName.SYMBOL_ACCESS_MODIFIER_CHECK.value
        diagnostic = Diagnostic(range, message, severity, code)
        self.diagnostics.append(diagnostic)

    def cyclic_dependency(self, range: vscode.Range, module_name: str, location_of_cyclic_import: vscode.Location):
        ' Cyclic dependency encountered during import resolution. '
        message = f'Cyclic dependency create at import of "{module_name}"'
        severity = DiagnosticSeverity.Error
        code = DiagnosticCodeName.CYCLIC_DEPENDENCY_CHECK.value
        related = DiagnosticRelatedInformation(
            location_of_cyclic_import, "Imported at")
        diagnostic = Diagnostic(range, message, severity,
                                code, relatedInformation=[related])
        self.diagnostics.append(diagnostic)

    def file_not_found(self, range: vscode.Range, file: Path):
        ' Generic file not found message. '
        message = f'File not found: "{file}"'
        severity = DiagnosticSeverity.Error
        code = DiagnosticCodeName.FILE_NOT_FOUND.value
        diagnostic = Diagnostic(range, message, severity, code)
        self.diagnostics.append(diagnostic)

    def referenced_symbol_type_check(self, range: vscode.Range, expected: ReferenceType, actual: ReferenceType):
        ' Used when the expected type given by a reference mismatches with the actually resolved symbol. '
        message = f'Expected symbol type is {expected.format_enum()} but the resolved symbol is of type {actual.format_enum()}'
        severity = DiagnosticSeverity.Error
        code = DiagnosticCodeName.REFERENCE_TYPE_CHECK.value
        diagnostic = Diagnostic(range, message, severity, code)
        self.diagnostics.append(diagnostic)

    def symbol_is_noverb_check(self, range: vscode.Range, symbol_name: str, lang: str = None, related_symbol_location: vscode.Location = None):
        ' Used when a reference to a symbol tagged with "noverb={langs...}" is made. '
        if lang:
            message = f'Symbol "{symbol_name}" is marked as noverb for the language "{lang}"'
        else:
            message = f'Symbol "{symbol_name}" is marked as noverb'
        severity = DiagnosticSeverity.Warning
        code = DiagnosticCodeName.REFERENCE_TO_NOVERB_CHECK.value
        related = []
        if related_symbol_location:
            related.append(DiagnosticRelatedInformation(
                related_symbol_location, 'Referenced symbol'))
        diagnostic = Diagnostic(range, message, severity,
                                code, relatedInformation=related)
        self.diagnostics.append(diagnostic)

    def redundant_import_check(self, range: vscode.Range, module_name: str, previously_at: vscode.Location = None):
        ' Used when a module is already imported by another module and can be removed. '
        message = f'Redundant import of module "{module_name}"'
        severity = DiagnosticSeverity.Warning
        code = DiagnosticCodeName.REDUNDANT_IMPORT_STATEMENT_CHECK.value
        if previously_at:
            related = [DiagnosticRelatedInformation(
                previously_at, 'Previously located here')]
        else:
            related = []
        tag = DiagnosticTag.Unnecessary
        diagnostic = Diagnostic(range, message, severity, code, tags=[
                                tag], relatedInformation=related)
        self.diagnostics.append(diagnostic)
