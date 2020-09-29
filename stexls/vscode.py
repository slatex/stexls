# Copied from https://microsoft.github.io/language-server-protocol/specifications/specification-3-14/
from __future__ import annotations
from typing import Optional, Union, Any, List, NewType, Generic, T, Tuple, Iterable
from pathlib import Path
import urllib
from enum import Enum

class SerializableEnum(Enum):
    def to_json(self):
        return self.value

    @classmethod
    def from_json(cls, json):
        return cls(json)


class Undefined:
    def __bool__(self) -> bool:
        return False

    def __repr__(self): return 'undefined'

    def to_json(self): return 'undefined'

    @staticmethod
    def from_json(json): return undefined

undefined = Undefined()

DocumentUri = NewType('DocumentUri', str)

ProgressToken = NewType('ProgressToken', Union[int, str])


class Position:
    ' Representation of a zero indexed line and character inside a file. '''
    def __init__(self, line: int, character: int):
        ''' Initializes the position with a line and character offset.
        Parameters:
            line: Zero indexed line of a file.
            character: 1 indexed character of the line.
        '''
        self.line = max(0, line)
        self.character = max(0, character)

    def __eq__(self, other: Position):
        return isinstance(other, Position) and self.line == other.line and self.character == other.character

    def __hash__(self):
        return hash(hash(self.line) ^ hash(self.character))

    def translate(self, lines: int = 0, characters: int = 0):
        """ Creates a copy of this position with the line and character
            attributes offsetted by the given amount.

        Parameters:
            lines (int): Optional line offset of the returned copy.
            characters (int): Optional character offset of the returned copy.

        Returns:
            Copy of this with line and character offsetted by the given
            amounts.

        Examples:
            >>> pos = Position(1, 2).translate(10, 20)
            >>> pos.line, pos.character
            (11, 22)
            >>> pos = Position(1, 2).translate(lines=10)
            >>> pos.line, pos.character
            (11, 2)
            >>> pos = Position(1, 2).translate(characters=20)
            >>> pos.line, pos.character
            (1, 22)
        """
        return Position(self.line + lines, self.character + characters)

    def compare_to(self, other: Position) -> int:
        ''' Compares two positions.

        Parameters:
            other: Other position to compare to.

        Returns:
            1. <0 if self < other.
            2. 0 if self = other.
            3. >0 if self > other.

        Examples:
            >>> Position(7, 3).compare_to(Position(7, 3))
            0
            >>> Position(1, 2).compare_to(Position(5, 42421))
            -4
            >>> Position(5, 7).compare_to(Position(2, 19))
            3
            >>> Position(1, 6).compare_to(Position(1, 4))
            2
            >>> Position(1, 6).compare_to(Position(1, 15))
            -9
        '''
        if self.line != other.line:
            return self.line - other.line
        elif self.character != other.character:
            return self.character - other.character
        else:
            return 0

    def is_after(self, other: Position) -> bool:
        ' Returns true if self appears after other. '
        return 0 < self.compare_to(other)

    def is_after_or_equal(self, other: Position) -> bool:
        ' Returns true if self appears after other or if they are equal. '
        return 0 <= self.compare_to(other)

    def is_before(self, other: Position) -> bool:
        ' Returns true if self appears before other. '
        return self.compare_to(other) < 0

    def is_before_or_equal(self, other: Position) -> bool:
        ' Returns true if self appears before other or if they are equal. '
        return self.compare_to(other) <= 0

    def is_equal(self, other: Position) -> bool:
        ' Returns true if line and character of both are the same. '
        return self.line == other.line and self.character == other.character

    def replace(self, line: Optional[int] = None, character: Optional[int] = None) -> Position:
        ''' Copies self and replaces the copies line and/or character.
        Parameters:
            line: Line of the copy if not None.
            character: Character of the copy if not None.
        Returns:
            Copy of self with line and/or character replaced.
        '''
        return Position(
            self.line if line is None else line,
            self.character if character is None else character)

    def copy_from(self, other: Position):
        ' Copies other line and character into self. '
        self.line = other.line
        self.character = other.character

    def copy(self) -> Position:
        ' Creates a copy of this position. '
        return Position(self.line, self.character)

    def format(self) -> str:
        return f'line {self.line}, column {self.character}'

    def __repr__(self):
        return f'[Position ({self.line} {self.character})]'

    def to_json(self) -> dict:
        return { 'line': self.line, 'character': self.character }

    @staticmethod
    def from_json(json: dict) -> Position:
        return Position(json['line'], json['character'])


class Range:
    ' Represents a range given by a start and end position. '
    def __init__(self, start: Position, end: Position = None):
        ''' Initializes the range.
        Parameters:
            start: Begin position.
            end: End position.
        '''
        assert isinstance(start, Position)
        self.start = start
        self.end = end or start

    def __eq__(self, other: Range):
        return isinstance(other, Range) and self.start == other.start and self.end == other.end

    def __hash__(self):
        return hash(hash(self.start) ^ hash(self.end))

    @property
    def length(self) -> Tuple[int, int]:
        ' Returns a tuple with 1st begin "length" of lines and 2nd being "length" of characters. Allows for easy comparision using builtin operators. '
        return self.end.line - self.start.line, self.end.character - self.start.character

    def is_empty(self) -> bool:
        ''' Checks wether the range is empty or not.
            The range is empty if start and end are equal.
        '''
        return self.start.equals(self.end)

    def is_single_line(self) -> bool:
        ' Returns true if the start and end positions are on the same line. '
        return self.start.line == self.end.line

    def contains(self, range: Union[Range, Position]) -> bool:
        '''
        >>> range = Range(Position(10, 5), Position(11, 10))
        >>> range.contains(Position(9, 213))
        False
        >>> range.contains(Position(12, 0))
        False
        >>> range.contains(Position(10, 4))
        False
        >>> range.contains(Position(10, 5))
        True
        >>> range.contains(Position(11, 10))
        True
        >>> range.contains(Position(11, 11))
        False
        >>> range.contains(Range(Position(11, 0), Position(11, 9)))
        True
        >>> range.contains(Range(Position(11, 10), Position(11, 12)))
        True
        >>> range.contains(Range(Position(11, 11), Position(11, 12)))
        False
        >>> range.contains(Range(Position(5, 11), Position(10, 12)))
        False
        >>> range.contains(Range(Position(10, 11), Position(10, 12)))
        True
        >>> range.contains(range)
        True
        '''
        if isinstance(range, Position):
            range: Position
            return self.start.is_before_or_equal(range) and self.end.is_after_or_equal(range)
        range: Range
        return self.start.is_before_or_equal(range.start) and self.end.is_after_or_equal(range.end)

    def union(self, other: Union[Range, Position]) -> Range:
        ''' Creates a new Range with the union of self and other.

        Parameters:
            other: Range to create union with.
                If other is a position, it will be converted to an empty range.

        Returns:
            New range representing the union of self and other.
            The union is given by the smaller start and larger end position of both.
        '''
        return Range(
            self.start.copy() if self.start.qual(other.start)
            else other.start.copy(),
            self.end.copy() if self.end.is_after_or_equal(other.end)
            else other.end.copy())

    def replace(self, start: Optional[Position] = None, end: Optional[Position] = None) -> Range:
        ''' Creates a copy with a new start and end.
        If start or end is not None they will be copied and
        not passed as is to the copied range.

        Parameters:
            start: Optional new start position.
            end: Optional new end position.

        Returns:
            New range instance with provided start and end.

        Examples:
            >>> range = Range(Position(10, 5), Position(16, 9))
            >>> range.replace(Position(1, 1), Position(2, 2))
            [Range (1 1) (2 2)]
            >>> range.replace(start=Position(2, 3))
            [Range (2 3) (16 9)]
            >>> range.replace(end=Position(11, 1))
            [Range (10 5) (11 1)]
        '''
        return Range(
            (self.start if start is None else start).copy(),
            (self.end if end is None else end).copy())

    def copy_from(self, other: Range):
        ' Replaces self start and end with copies of other start and end. '
        self.start = other.start.copy()
        self.end = other.end.copy()

    def copy(self) -> Range:
        ' Creates a deep copy of self. '
        return Range(self.start.copy(), self.end.copy())

    def split(self, index: int) -> Tuple[Range, Range]:
        ''' Splits the range at the given index.

        If the split lies outside of the range, one range will be the
        original range, and the other will be empty at the
        side which was outside.

        Parameters:
            index (int): Index offset at which the range should be split

        Raises:
            ValueError: If index is negative.

        Returns:
            Tuple[Range, Range]: First range is in range (self.start, self.start + index)
                and the other is (self.start + index, self.end).

        Examples:
            >>> range = Range(Position(5, 5), Position(6, 10))
            >>> first, second = range.split(10)
            >>> first
            [Range (5 5) (5 15)]
            >>> second
            [Range (5 15) (6 10)]
            >>> range = Range(Position(2, 1), Position(2 5))
            >>> first, second = range.split(5)
            >>> first
            [Range (2 1) (2 5)]
            >>> second
            [Range (2 5) (2 5)]
        '''
        if index < 0:
            raise ValueError(f'Unable to split on negative index {index}.')
        split = self.start.replace(character=self.start.character + index)
        if self.end.is_before(split):
            return self.copy(), self.replace(start=self.end)
        return self.replace(end=split), self.replace(start=split)

    def translate(self, lines: int = 0, characters: int = 0) -> Range:
        ' Translates start and end positions by the given line and character offsets and returns a new range. '
        return Range(self.start.translate(lines, characters), self.end.translate(lines, characters))

    @staticmethod
    def big_union(rangesOrPositions: List[Union[Range, Position]]) -> Optional[Range]:
        ''' Creates the big union of all ranges and positions given.
            The big union is given by the range formed by the smallest
            and largest position in the list.
            If the big union can't be created None is returned.
        '''
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

    def to_json(self) -> dict:
        return { 'start': self.start.to_json(), 'end': self.end.to_json() }

    @staticmethod
    def from_json(json: dict) -> Range:
        return Range(Position.from_json(json['start']), Position.from_json(json['end']))


class Location:
    def __init__(self, uri: DocumentUri, positionOrRange: Union[Position, Range]):
        if urllib.parse.urlparse(uri).scheme != 'file':
            raise ValueError(f'uri argument is not a file uri ({uri})')
        self.uri = DocumentUri(uri)
        if isinstance(positionOrRange, Position):
            self.range = Range(positionOrRange, positionOrRange)
        else:
            assert isinstance(positionOrRange, Range), "Invalid Location initialization: positionOrRange must be of type Position or Range."
            self.range = positionOrRange

    def copy(self) -> Location:
        return Location(self.uri, self.range.copy())

    def __eq__(self, other: Location):
        return isinstance(other, Location) and self.uri == other.uri and self.range == other.range

    def __hash__(self):
        return hash(hash(self.uri) ^ hash(self.range))

    def read(self, lines: Optional[List[str]] = None) -> str:
        ''' Opens the file and returns the text at the range of the location.

        Parameters:
            lines: Optional content of the file. If None, then the file will be read from disk with open().

        Returns:
            The range this location includes.
            None if the file does not exist or the location can\'t be read.
        '''
        try:
            if lines is None:
                with open(self.path, 'r') as fd:
                    lines = fd.readlines()
            if self.range.is_single_line():
                return lines[self.range.start.line][self.range.start.character:self.range.end.character]
            else:
                lines = lines[self.range.start.line:self.range.end.line+1]
                return '\n'.join(lines)[self.range.start.character:-self.range.end.character]
        except (IndexError, FileNotFoundError):
            return None

    @property
    def path(self) -> Path:
        ' Returns the uri property as a posix path. '
        return Path(urllib.parse.urlparse(self.uri).path)

    def contains(self, loc: Union[Location, Range, Position]) -> bool:
        ' Returns True if the loc argument is contained within this location\'s range and the file is corrent if given. '
        if isinstance(loc, (Range, Position)):
            return self.range.contains(loc)
        return self.uri == loc.uri and self.range.contains(loc.range)

    def format_link(self, relative: bool = False, relative_to: Path = None) -> str:
        """ Formats this location object as a clickable link. E.g.: "/path/to/file:<line>"

        Parameters:
            relative: If True, then the path is formated relative to current working dir.

        Returns:
            String formatted as a clickable link.
        """
        range = self.range.translate(1, 1)
        path = self.path
        if relative:
            path = path.relative_to(relative_to or Path.cwd())
        path = path.as_posix().replace('\\ ', ' ').replace(' ', '\\ ') # two times to prevent errors with already escaped paths
        return f'{path}:{range.start.line}:{range.start.character}'

    def replace(self, uri: DocumentUri = None, positionOrRange: Union[Position, Range] = None):
        ''' Creates a copy of this location object and replaces uri and/or range properties if given.

        Parameters:
            uri: Optional uri replacement.
            positionOrRange: Optional range replacement.

        Returns:
            Location: Copy of this location with uri and/or range replaced.
        '''
        return Location(
            uri or self.uri,
            (positionOrRange or self.range).copy())

    def __repr__(self):
        return f'[Location uri="{self.uri}" range={self.range}]'

    def to_json(self) -> dict:
        return { 'uri': str(self.uri), 'range': self.range.to_json() }

    @staticmethod
    def from_json(json: dict) -> Location:
        return Location(DocumentUri(json['uri']), Range.from_json(json['range']))


class LocationLink:
    def __init__(
        self,
        targetUri: DocumentUri,
        targetRange: Range,
        targetSelectionRange: Range,
        originSelectionRange: Optional[Range] = undefined):
        self.targetUri = targetUri
        self.targetRange = targetRange
        self.targetSelectionRange = targetSelectionRange
        if originSelectionRange:
            self.originSelectionRange = originSelectionRange

    def to_json(self) -> dict:
        json = { 'targetUri': str(self.targetUri), 'targetRange': self.targetRange.to_json(), 'targetSelectionRange': self.targetRange.to_json() }
        if getattr(self, 'originSelectionRange', None):
            json['originSelectionRange'] = self.originSelectionRange.to_json()
        return json

    @staticmethod
    def from_json(json: dict) -> LocationLink:
        return LocationLink(
            targetUri=DocumentUri(json['targetUri']),
            targetRange=Range.from_json(json['targetRange']),
            targetSelectionRange=Range.from_json(json['targetSelectionRange']),
            originSelectionRange=undefined if 'originSelectionRange' not in json else Range.from_json(json['originSelectionRange']))


class TextDocumentIdentifier:
    def __init__(self, uri: DocumentUri):
        self.uri = uri

    @property
    def path(self) -> Path:
        ' Converts the uri to a path object. '
        p = urllib.parse.urlparse(self.uri)
        return Path(p.path)

    def to_json(self) -> dict:
        return { 'uri': str(self.uri) }

    @staticmethod
    def from_json(json: dict) -> TextDocumentIdentifier:
        return TextDocumentIdentifier(DocumentUri(json['uri']))


class DiagnosticSeverity(SerializableEnum):
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

    def to_json(self) -> dict:
        return { 'location': self.location.to_json(), 'message': self.message }


class DiagnosticTag(SerializableEnum):
    Unnecessary: int = 1
    Deprecated: int = 2


class Diagnostic:
    def __init__(
        self,
        range: Range,
        message: str,
        severity: DiagnosticSeverity = undefined,
        code: Union[int, str] = undefined,
        source: str = undefined,
        tags: List[DiagnosticTag] = undefined,
        relatedInformation: List[DiagnosticRelatedInformation] = undefined):
        self.range = range
        self.message = message
        if severity is not undefined:
            self.severity = severity
        if code is not undefined:
            self.code = code
        if source is not undefined:
            self.source = source
        if tags is not undefined:
            self.tags = tags
        if relatedInformation is not undefined:
            self.relatedInformation = relatedInformation

    def to_json(self) -> dict:
        json = {
            'range': self.range.to_json(),
            'message': self.message,
            'severity': self.severity.to_json(),
        }
        if getattr(self, 'tags', undefined) is not undefined:
            json['tags'] = [ tag.to_json() for tag in self.tags ]
        if getattr(self, 'relatedInformation', undefined) is not undefined:
            json['relatedInformation'] = [ info.to_json() for info in self.relatedInformation ]
        return json


class MessageType(SerializableEnum):
    Error: int = 1
    Warning: int = 2
    Info: int = 3
    Log: int = 4


class MessageActionItem:
    def __init__(self, title: str):
        self.title = title

    def to_json(self) -> dict:
        return { 'title': self.title }

    @staticmethod
    def from_json(json: dict) -> MessageActionItem:
        return MessageActionItem(str(json['title']))


class TextDocumentItem:
    def __init__(self, uri: DocumentUri, languageId: str, version: int, text: str):
        self.uri = uri
        self.languageId = languageId
        self.version = version
        self.text = text

    @property
    def path(self):
        ' Converts the uri to a Path object. '
        p = urllib.parse.urlparse(self.uri)
        return Path(p.path)

    def to_json(self) -> dict:
        return { 'uri': self.uri, 'languageId': self.languageId, 'version': self.version, 'text': self.text }

    @staticmethod
    def from_json(json: dict) -> TextDocumentItem:
        return TextDocumentItem(str(json['uri']), languageId=str(json['languageId']), version=int(json['version']), text=str(json['text']))


class CompletionTriggerKind(SerializableEnum):
    Invoked = 1
    TriggerCharacter = 2
    TriggerForIncompleteCompletions = 3


class CompletionContext:
    def __init__(
        self,
        triggerKind: CompletionTriggerKind,
        triggerCharacter: str = undefined):
        self.triggerKind = triggerKind
        if triggerCharacter != undefined:
            self.triggerCharacter = triggerCharacter

    def to_json(self) -> dict:
        json = { 'triggerKind': self.triggerKind.to_json() }
        if getattr(self, 'triggerCharacter', undefined) != undefined:
            json['triggerCharacter'] = self.triggerCharacter

    @staticmethod
    def from_json(json) -> CompletionContext:
        return CompletionContext(
            CompletionTriggerKind.from_json(json.get('triggerKind')),
            json.get('triggerCharacter', undefined))


class InsertTextFormat(SerializableEnum):
    PlainText = 1
    Snippet = 2


class CompletionItemTag(SerializableEnum):
    Deprecated = 1


class TextEdit:
    def __init__(self, range: Range, newText: str):
        self.range = range
        self.newText = newText

    def to_json(self) -> dict:
        return { 'range': self.range.to_json(), 'newText': self.newText }

    @staticmethod
    def from_json(dict) -> TextEdit:
        return TextEdit(Range.from_json(dict['range']), str(dict['newText']))


class CompletionItemKind(SerializableEnum):
	Text = 1
	Method = 2
	Function = 3
	Constructor = 4
	Field = 5
	Variable = 6
	Class = 7
	Interface = 8
	Module = 9
	Property = 10
	Unit = 11
	Value = 12
	Enum = 13
	Keyword = 14
	Snippet = 15
	Color = 16
	File = 17
	Reference = 18
	Folder = 19
	EnumMember = 20
	Constant = 21
	Struct = 22
	Event = 23
	Operator = 24
	TypeParameter = 25


class CompletionItem:
    def __init__(
        self,
        label: str,
        kind: CompletionItemKind = undefined,
        tags: List[CompletionItemTag] = undefined,
        detail: str = undefined,
        documentation: str = undefined,
        deprecated: bool = undefined,
        preselect: bool = undefined,
        sortText: bool = undefined,
        filterText: str = undefined,
        insertText: str = undefined,
        insertTextFormat: InsertTextFormat = undefined,
        textEdit: TextEdit = undefined,
        additionalTextEdtits: List[TextEdit] = undefined,
        commitCharacters: List[str] = undefined,
        command = undefined,
        data = undefined):
        self.label = label
        if kind != undefined:
            self.kind = kind
        if tags != undefined:
            self.tags = tags
        if detail != undefined:
            self.detail = detail
        if documentation != undefined:
            self.documentation = documentation
        if deprecated != undefined:
            self.deprecated = deprecated
        if preselect != undefined:
            self.preselect = preselect
        if sortText != undefined:
            self.sortText = sortText
        if filterText != undefined:
            self.filterText = filterText
        if insertText != undefined:
            self.insertText = insertText
        if insertTextFormat != undefined:
            self.insertTextFormat = insertTextFormat
        if textEdit != undefined:
            self.textEdit = textEdit
        if additionalTextEdtits != undefined:
            self.additionalTextEdtits = additionalTextEdtits
        if commitCharacters != undefined:
            self.commitCharacters = commitCharacters
        if command != undefined:
            self.command  = command
        if data != undefined:
            self.data  = data

    def to_json(self) -> dict:
        json = { 'label': self.label }
        if self.kind != undefined:
            json['kind'] = self.kind
        if self.tags != undefined:
            json['tags'] = self.tags
        if self.detail != undefined:
            json['detail'] = self.detail
        if self.documentation != undefined:
            json['documentation'] = self.documentation
        if self.deprecated != undefined:
            json['deprecated'] = self.deprecated
        if self.preselect != undefined:
            json['preselect'] = self.preselect
        if self.sortText != undefined:
            json['sortText'] = self.sortText
        if self.filterText != undefined:
            json['filterText'] = self.filterText
        if self.insertText != undefined:
            json['insertText'] = self.insertText
        if self.insertTextFormat != undefined:
            json['insertTextFormat'] = self.insertTextFormat
        if self.textEdit != undefined:
            json['textEdit'] = self.textEdit
        if self.additionalTextEdtits != undefined:
            json['additionalTextEdtits'] = self.additionalTextEdtits
        if self.commitCharacters != undefined:
            json['commitCharacters'] = self.commitCharacters
        if self.command != undefined:
            json['command'] = self.command
        if self.data != undefined:
            json['data'] = self.data
        return json

    @staticmethod
    def from_json(json) -> CompletionItem:
        raise ValueError('CompletionItem cannot be deserialized.')

    def __repr__(self):
        return f'[CompletionItem {self.label}]'


class CompletionList:
    def __init__(self, isComplete: bool, items: List[CompletionItem]):
        self.isComplete = isComplete
        self.items = items

    def to_json(self) -> dict:
        return {
            'isComplete': self.isComplete,
            'items': [ item.to_json() for item in self.items ]}

    @staticmethod
    def from_json(json):
        raise ValueError('CompletionList cannot be deserialized.')


class WorkDoneProgressBegin:
    def __init__(
        self,
        title: str,
        percentage: int = undefined,
        message: str = undefined,
        cancellable: bool = undefined):
        self.kind = 'begin'
        self.title = title
        if percentage != undefined:
            self.percentage = percentage
        if message != undefined:
            self.message = message
        if cancellable != undefined:
            self.cancellable = cancellable

    def to_json(self) -> dict:
        json = {
            'kind': self.kind,
            'title': self.title,
        }
        if getattr(self, 'percentage', undefined) != undefined:
            json['percentage'] = self.percentage
        if getattr(self, 'message', undefined) != undefined:
            json['message'] = self.message
        if getattr(self, 'cancellable', undefined) != undefined:
            json['cancellable'] = self.cancellable
        return json

    @staticmethod
    def from_json(json) -> WorkDoneProgressBegin:
        return WorkDoneProgressBegin(
            json['title'],
            json.get('percentage', undefined),
            json.get('message', undefined),
            json.get('cancellable', undefined))


class WorkDoneProgressReport:
    def __init__(
        self,
        percentage: int = undefined,
        message: str = undefined,
        cancellable: bool = undefined):
        self.kind = 'report'
        if percentage != undefined:
            self.percentage = percentage
        if message != undefined:
            self.message = message
        if cancellable != undefined:
            self.cancellable = cancellable

    def __repr__(self): return str(self.to_json())

    def to_json(self) -> dict:
        json = { 'kind': self.kind }
        if getattr(self, 'percentage', undefined) != undefined:
            json['percentage'] = self.percentage
        if getattr(self, 'message', undefined) != undefined:
            json['message'] = self.message
        if getattr(self, 'cancellable', undefined) != undefined:
            json['cancellable'] = self.cancellable
        return json

    @staticmethod
    def from_json(json) -> WorkDoneProgressBegin:
        return WorkDoneProgressBegin(
            json.get('percentage', undefined),
            json.get('message', undefined),
            json.get('cancellable', undefined))


class WorkDoneProgressEnd:
    def __init__(
        self,
        message: str = undefined):
        self.kind = 'end'
        if message != undefined:
            self.message = message

    def to_json(self) -> dict:
        json = {
            'kind': self.kind,
        }
        if getattr(self, 'message', undefined) != undefined:
            json['message'] = self.message
        return json

    @staticmethod
    def from_json(json) -> WorkDoneProgressBegin:
        return WorkDoneProgressBegin(
            json.get('message', undefined))


class VersionedTextDocumentIdentifier(TextDocumentIdentifier):
    def __init__(self, uri: DocumentUri, version: Optional[int]):
        super().__init__(uri)
        self.version = version

    def to_json(self) -> dict:
        return { 'uri': self.uri, 'version': self.version }

    @staticmethod
    def from_json(json) -> VersionedTextDocumentIdentifier:
        return VersionedTextDocumentIdentifier(json['uri'], json['version'])


class SymbolKind(SerializableEnum):
    Array=17
    Boolean=16
    Class=4
    Constant=13
    Constructor=8
    Enum=9
    EnumMember=21
    Event=23
    Field=7
    File=0
    Function=11
    Interface=10
    Key=19
    Method=5
    Module=1
    Namespace=2
    Null=20
    Number=15
    Object=18
    Operator=24
    Package=3
    Property=6
    String=14
    Struct=22
    TypeParameter=25
    Variable=12


class SymbolTag(SerializableEnum):
    Deprecated=1


class DocumentSymbol:
    def __init__(self, name: str, detail: str, kind: SymbolKind, range: Range, selectionRange: Range):
        self.name = name
        self.children: List[DocumentSymbol] = []
        self.detail: str = detail
        self.kind: SymbolKind = kind
        self.range: Range = range
        self.selectionRange: Range = selectionRange
        self.tags: List[SymbolTag] = []

    def to_json(self) -> dict:
        j = {
            'name': self.name,
            'detail': self.detail,
            'kind': self.kind.to_json(),
            'range': self.range.to_json(),
            'selectionRange': self.selectionRange.to_json(),
            'children': [ child.to_json() for child in self.children ]
        }
        if self.tags:
            j['tags'] = [ tag.to_json() for tag in self.tags ]
        return j

    def __repr__(self):
        return f'[DocumentSymbol {self.name} of {self.kind} at {self.range}]'


class SymbolInformation:
    def __init__(self, name: str, kind: SymbolKind, location: Location, containerName: str = undefined):
        self.name = name
        self.kind = kind
        self.location = location
        if containerName:
            self.containerName = containerName

    def to_json(self) -> dict:
        j = {
            'name': self.name,
            'kind': self.kind.to_json(),
            'location': self.location.to_json()
        }
        if getattr(self, 'containerName', undefined):
            j['containerName'] = self.containerName
        return j