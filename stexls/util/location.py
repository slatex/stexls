''' The location module contains simple structures that
represent positions or ranges in files. '''
from __future__ import annotations
from typing import Union, Optional, List, Tuple
from pathlib import Path
import urllib

__all__ = ['Position', 'Range', 'Location']


class Position:
    ' Representation of a zero indexed line and character inside a file. '''
    def __init__(self, line: int, character: int):
        ''' Initializes the position with a line and character offset.
        Parameters:
            line: Zero indexed line of a file.
            character: Zero indexed character of the line.
        '''
        self.line = line
        self.character = character
    
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
        ' Translates start and end positions by the given line and character offsets. '
        return Range(self.start.translate(lines, characters), self.end.translate(lines, characters))

    @staticmethod
    def big_union(rangesOrPositions: List[Union[Range, Position]]) -> Optional[Range]:
        ''' Creates the big union of all ranges and positions given.
            The big union is given by the range formed by the smallest
            and largest position in the list.
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
    def __init__(self, uri: Path, positionOrRange: Union[Position, Range]):
        self.uri = uri
        if isinstance(positionOrRange, Position):
            self.range = Range(positionOrRange, positionOrRange)
        else:
            assert isinstance(positionOrRange, Range), "Invalid Location initialization: positionOrRange must be of type Position or Range."
            self.range = positionOrRange

    def contains(self, loc: Union[Location, Range, Position]) -> bool:
        if isinstance(loc, (Range, Position)):
            return self.range.contains(loc)
        return self.uri == loc.uri and self.range.contains(loc.range)

    def format_link(self, relative: bool = False, relative_to: Path = None) -> str:
        range = self.range.translate(1, 1)
        path = self.uri.relative_to(relative_to or Path.cwd()) if relative else self.uri
        path = path.as_posix().replace('\\ ', ' ').replace(' ', '\\ ') # two times to prevent errors with already escaped paths
        return f'{path}:{range.start.line}:{range.start.character}'

    def replace(self, uri: Path = None, positionOrRange: Union[Position, Range] = None):
        ''' Creates a copy of this location and replaces uri and/or range if given.

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
        return {'uri': str(self.uri.as_uri()), 'range': self.range.to_json() }
    
    @staticmethod
    def from_json(json: dict) -> Location:
        p = urllib.parse.urlparse(json['uri'])
        return Location(Path(p.path), Range.from_json(json['range']))

