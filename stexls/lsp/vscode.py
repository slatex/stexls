# Copied from https://microsoft.github.io/language-server-protocol/specifications/specification-3-14/

from typing import Optional, Union, Any, List


class Position:
    def __init__(self, line: int, character: int):
        self.line = line
        self.character = character

    def compare_to(self, other: Position) -> int:
        if self.line != other.line:
            return self.line - other.line
        elif self.character != other.character:
            return self.character - other.character
        else:
            return 0

    def is_after(self, other: Position) -> bool:
        return 0 < self.compare_to(other)

    def is_after_or_equal(self, other: Position) -> bool:
        return 0 <= self.compare_to(other)

    def is_before(self, other: Position) -> bool:
        return self.compare_to(other) < 0

    def is_before_or_equal(self, other: Position) -> bool:
        return self.compare_to(other) <= 0

    def is_equal(self, other: Position) -> bool:
        return self.line == other.line and self.character == other.character

    def replace(self, line: Optional[int] = None, character: Optional[int] = None) -> Position:
        return Position(
            self.line if line is None else line,
            self.character if character is None else character)

    def copy_from(self, other: Position):
        self.line = other.line
        self.character = other.character

    def copy(self) -> Position:
        return Position(self.line, self.character)

    def __repr__(self):
        return f'[Position ({self.line} {self.character})]'


class Range:
    def __init__(self, start: Position, end: Position):
        self.start = start
        self.end = end

    def is_empty(self) -> bool:
        return self.start.equals(self.end)

    def is_single_line(self) -> bool:
        return self.start.line == self.end.line

    def union(self, other: Union[Range, Position]) -> Range:
        return Range(
            self.start.copy() if self.start.qual(other.start)
            else other.start.copy(),
            self.end.copy() if self.end.is_after_or_equal(other.end)
            else other.end.copy())

    def replace(self, start: Optional[Position] = None, end: Optional[Position] = None) -> Range:
        return Range(
            (self.start if start is None else start).copy(),
            (self.end if end is None else end).copy())

    def copy_from(self, other: Range):
        self.start = other.start.copy()
        self.end = other.end.copy()

    def copy(self) -> Range:
        return Range(self.start.copy(), self.end.copy())

    @staticmethod
    def big_union(rangesOrPositions: List[Union[Range, Position]]) -> Optional[Range]:
        if not rangesOrPositions:
            return None
        default = rangesOrPositions[0]
        if isinstance(default, Position):
            accmin: Position = default
            accmax: Position = default
        else:
            accmin: Position = default.start
            accmax: Position = default.end
        for x in rangesOrPositions[1:]:
            assert isinstance(x, (Position, Range)), "Invalid type in array."
            if isinstance(x, Position):
                if accmin is None or x.is_before(accmin):
                    accmin = x
                if accmax is None or x.is_after(accmax):
                    accmax = x
            else:
                if accmin is None or x.start.is_before(accmin):
                    accmin = x.start
                if accmax is None or x.end.is_after(accmax):
                    accmax = x.end
        return Range(accmin.copy(), accmax.copy())

    def __repr__(self):
        return f'[Range ({self.start.line} {self.start.character}) ({self.end.line} {self.end.character})]'


class Location:
    def __init__(self, uri: str, positionOrRange: Union[Position, Range]):
        self.uri = uri
        if isinstance(positionOrRange, Position):
            self.range = Range(positionOrRange, positionOrRange)
        else:
            self.range = positionOrRange

    def __repr__(self):
        return f'[Location uri="{self.uri}" range={self.range}]'


class LocationLink:
    def __init__(
        self,
        targetUri: str,
        originalSelectionRange: Optional[Range],
        targetRange: Range,
        targetSelectionRange: Range):
        self.targetUri = targetUri
        self.targetRange = targetRange
        self.targetSelectionRange = targetSelectionRange
        if originalSelectionRange:
            self.originalSelectionRange = originalSelectionRange


class Diagnostic:
    def __init__(
        self,
        range: Range,
        severity: Optional[int],
        code: Optional[Union[int, str]],
        source: Optional[str],
        message: str,
        relatedInformation: Optional[List['DiagnosticRelatedInformation']]):
        self.range = range
        if severity is not None:
            self.severity = severity
        if code is not None:
            self.code = code
        if source is not None:
            self.source = source
        self.message = message
        if relatedInformation is not None:
            self.relatedInformation = relatedInformation


class DiagnosticSeverity:
    Error: int = 1
    Warning: int = 2
    Information: int = 3
    Hint: int = 4


class DiagnosticRelatedInformation:
    def __init__(
        self,
        location: Location,
        message: str):
        self.location = location
        self.message = message


class Command:
    def __init__(
        self,
        title: str,
        command: str,
        arguments: Optional[List[Any]]):
        self.title = title
        self.command = command
        if arguments is not None:
            self.arguments = arguments


class TextEdit:
    def __init__(
        self,
        range: Range,
        newText: str):
        self.range = range
        self.newText = newText


class TextDocumentEdit:
    def __init__(
        self,
        textDocument: 'VersionedTextDocumentIdentifier',
        edits: List[TextEdit]):
        self.textDocument = textDocument
        self.edits = edits


class CreateFileOptions:
    def __init__(
        self,
        overwrite: Optional[bool],
        ignoreIfExists: Optional[bool]):
        if overwrite is not None:
            self.overwrite = overwrite
        if ignoreIfExists is not None:
            self.ignoreIfExists = ignoreIfExists


class CreateFile:
    def __init__(
        self,
        uri: str,
        options: Optional[CreateFileOptions]):
        self.kind = 'create'
        self.uri = uri
        if options is not None:
            self.options = options


class RenameFileOptions:
    def __init__(
        self,
        overwrite: Optional[bool],
        ignoreIfExists: Optional[bool]):
        if overwrite is not None:
            self.overwrite = overwrite
        if ignoreIfExists is not None:
            self.ignoreIfExists = ignoreIfExists


class RenameFile:
    def __init__(
        self,
        oldUri: str,
        newUri: str,
        options: Optional[RenameFileOptions]):
        self.kind = 'rename'
        self.oldUri = oldUri
        self.newUri = newUri
        if options is not None:
            self.options = options


class DeleteFileOptions:
    def __init__(
        self,
        recursive: Optional[bool],
        ignoreIfNotExists: Optional[bool]):
        if recursive is not None:
            self.recursive = recursive
        if ignoreIfNotExists is not None:
            self.ignoreIfExists = ignoreIfNotExists


class DeleteFile:
    def __init__(
        self,
        uri: str,
        options: Optional[DeleteFileOptions]):
        self.uri = uri
        if options is not None:
            self.options = options
