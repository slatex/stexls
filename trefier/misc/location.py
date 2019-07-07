from __future__ import annotations
from typing import Union, Tuple, List, Optional

import os.path as _path
import json
import copy


class Position:
    def __init__(self, line: int = 1, column: int = 1):
        """
        A position in a file.
        :param line: 1-indexed line
        :param column: 1-indexed column
        """
        self.line = line
        self.column = column

    def copy_from(self, that: Position):
        self.line = that.line
        self.column = that.column

    def __repr__(self):
        return f'Position(line={self.line}, column={self.column})'
    
    def __iter__(self):
        """ Iterates through line and column members. """
        yield self.line
        yield self.column
    
    def __le__(self, other: Position) -> bool:
        """
        Tests if a position occurs before another position.
        :param other Other position
        :returns True if on a previous line or if on the same line, then the column needs to occur before
        """
        return self.before(other)

    def __gt__(self, other: Position) -> bool:
        """
        Tests if a position occurs after another position.
        :param other Other position
        :returns True if on a previous line or if on the same line, then the column needs to occur before
        """
        return self.after(other)
    
    def __eq__(self, other: Position) -> bool:
        return self.line == other.line and self.column == other.column
    
    def __ne__(self, other: Position) -> bool:
        return not (self == other)
    
    def to_json(self):
        return json.dumps(self.__dict__)
    
    def __hash__(self):
        return hash(self.line) ^ hash(self.column)
    
    def before(self, other: Position, strict=False) -> bool:
        """
        :param other Other position
        :param strict If True, only returns True if column < other.column if they are on the same line
        :returns True if this is occurs before the other position.
        """
        return self.line < other.line or (self.line == other.line and (self.column < other.column or (not strict and self.column == other.column)))
    
    def after(self, other: Position, strict=False) -> bool:
        """
        :param other Other position
        :param strict If True, only returns True if column > other.column if they are on the same line
        :returns True if this occurs after the other.
        """
        return other.line < self.line or (self.line == other.line and (other.column < self.column or (not strict and other.column == self.column)))
    
    def append_to_file(self, file) -> str:
        """
        Appends the location to a file in order to create a link to the position.
        :returns Link to the location in file:line:column format
        """
        return f'{file}:{self.line}:{self.column}'


class Range:
    def __init__(self, begin: Position, end: Optional[Position] = None):
        """
        A range between two positions
        :param begin: Begin of the range
        :param end: End of the range
        """
        if not isinstance(begin, Position):
            raise ValueError(f"begin must be of type Position. Found: {str(type(begin))}")
        if end is not None and not isinstance(end, Position):
            raise ValueError(f"end must be of type Position. Found: {str(type(end))}")
        self.begin = begin
        self.end = end or begin

    def copy_from(self, that: Range):
        self.begin = Position(0, 0)
        self.begin.copy_from(that.begin)
        self.end = Position(0, 0)
        self.end.copy_from(that.end)

    def __le__(self, other: Union[Range, Position]) -> bool:
        return self.before(other)

    def __gt__(self, other: Union[Range, Position]) -> bool:
        return self.after(other)
    
    def __eq__(self, other: Range) -> bool:
        if not isinstance(other, Range):
            return False
        return self.begin == other.begin and self.end == other.end
    
    def __ne__(self, other: Range) -> bool:
        return not (self == other)

    def union(self, other: Range) -> Range:
        return Range(copy.copy(min([self.begin, other.begin])), copy.copy(max([self.end, other.end])))
    
    def before(self, other: Union[Range, Position], strict: bool = False) -> bool:
        """
        Returns whether a range or a position occurs before this range begins.
        :param other: A range or position
        :param strict: If True, checks positions inclusively
        :return: True if other occurs before self
        """
        if isinstance(other, Position):
            return self.end.before(other, strict=strict)
        elif isinstance(other, Range):
            return self.end.before(other.begin, strict=strict)
        else:
            raise ValueError("other must be of type Range or Position")
    
    def after(self, other: Union[Range, Position], strict: bool = False) -> bool:
        """
        Returns whether a range or a position occurs after this range begins.
        :param other: A range or position
        :param strict: If True, checks positions inclusively
        :return: True if other occurs after self
        """
        if isinstance(other, Position):
            return self.begin.after(other, strict=strict)
        elif isinstance(other, Range):
            return self.begin.after(other.end, strict=strict)
        else:
            raise ValueError("other must be of type Range or Position")
    
    def contains(self, other: Union[Range, Position], strict: bool = False) -> bool:
        """
        Returns whether a range or a position is completely contained withing this range
        :param other: A range or position
        :param strict: If True, checks positions inclusively. Other may also touch the edges of this range.
        :return: True if other occurs before self
        """
        if isinstance(other, Position):
            return self.begin.before(other, strict=strict) and self.end.after(other, strict=strict)
        elif isinstance(other, Range):
            return self.begin.before(other.begin, strict=strict) and self.end.after(other.end, strict=strict)
        else:
            raise ValueError("other must be of type Range or Position")
    
    def to_json(self):
        return json.dumps(self, default=lambda obj: obj.__dict__)
    
    def __hash__(self):
        return hash(self.begin) ^ hash(self.end)
    
    def __iter__(self):
        yield self.begin
        yield self.end

    def __repr__(self):
        return f'Range(begin={self.begin}, end={self.end})'


class Location:
    def __init__(self, file: str, range: Range, offset: Tuple[int, int] = None):
        """ Creates a range in a file.
        Arguments:
            :param file: The target file.
            :param range: The range in the file.
            :param offset: Optional precomputed character offset representation for the range: tuple(begin, end).
                            If None then the offset will be computed by loading the file.
        """
        self.file = _path.abspath(file)
        self.range = range
        self._offset = offset
        self._text = None

    def copy_from(self, that: Location):
        self.file = that.file
        self.range = Range(Position(0, 0), Position(0, 0))
        self.range.copy_from(that.range)
        self._offset = that._offset
        self._text = that._text

    def union(self, other: Union[Location, Range]) -> Location:
        other_range = other if isinstance(other, Range) else other.range
        return Location(self.file, self.range.union(other_range))

    @staticmethod
    def reduce_union(locations: List[Location]) -> Location:
        """ Reduces the union of all locations in the list. """
        assert locations
        location = locations[0]
        for that in locations[1:]:
            location = location.union(that)
        return location
    
    @property
    def offset(self) -> Tuple[int, int]:
        """ Returns the range as a character offset tuple (begin:int, end:int) """
        if self._offset is not None:
            return self._offset
        with open(self.file) as ref:
            lines = ref.read().split('\n')
            self._offset = (
                sum(map(len,
                        lines[:self.range.begin.line - 1])) + self.range.begin.line - 1 + self.range.begin.column - 1,
                sum(map(len,
                        lines[:self.range.end.line - 1])) + self.range.end.line - 1 + self.range.end.column - 1
            )
        return self._offset
    
    @property
    def text(self) -> str:
        """ Returns the string in the range by opening the file. """
        try:
            if self._text is not None:
                return self._text
            begin, end = self.offset
            with open(self.file) as ref:
                self._text = ref.read()[begin:end]
            return self._text
        except FileNotFoundError:
            return None
    
    def to_json(self):
        return f'{{"file":"{self.file}","range":{self.range.to_json()}}}'
    
    def to_link(self) -> str:
        return self.range.begin.append_to_file(self.file)
    
    def __repr__(self):
        return self.to_link()

    @property
    def relative(self) -> Location:
        """ :returns Copy of the same location, but the file path is relative. """
        location = Location(self.file, self.range, self._offset)
        location._text = self._text
        location.file = _path.relpath(self.file)
        return location
    
    def __eq__(self, other):
        if other is None:
            return False
        if not isinstance(other, Location):
            return False
        return _path.abspath(self.file) == _path.abspath(other.file) and self.range == other.range
    
    def __ne__(self, other):
        return not (self == other)
    
    def __hash__(self):
        return hash(_path.abspath(self.file)) ^ hash(self.range)
