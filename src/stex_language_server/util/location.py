from __future__ import annotations
from typing import Union, Optional, List

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
    
    def compare_to(self, other: Position) -> int:
        ''' Compares two positions.
        Parameters:
            other: Other position to compare to.
        Returns:
            1. <0 if self < other.
            2. 0 if self = other.
            3. >0 if self > other.
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

        
class Range:
    ' Represents a range given by a start and end position. '
    def __init__(self, start: Position, end: Position):
        ''' Initializes the range.
        Parameters:
            start: Begin position.
            end: End position.
        '''
        self.start = start
        self.end = end
    
    def is_empty(self) -> bool:
        ''' Checks wether the range is empty or not.
            The range is empty if start and end are equal.
        '''
        return start.equals(end)
    
    def is_single_line(self) -> bool:
        ' Returns true if the start and end positions are on the same line. '
        return self.start.line == self.end.line
    
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

    @staticmethod
    def big_union(rangesOrPositions: List[Union[Range, Position]]) -> Range:
        ''' Creates the big union of all ranges and positions given.
            The big union is given by the range formed by the smallest
            and largest position in the list.
        '''
        if not rangesOrPositions:
            raise ValueError('List of ranges may not be empty.')
        accmin: Position = None
        accmax: Position = None
        for x in rangesOrPositions[1:]:
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
        assert accmin is not None
        assert accmax is not None
        return Range(accmin.copy(), accmax.copy())


class Location:
    def __init__(self, uri: str, positionOrRange: Union[Position, Range]):
        self.uri = uri
        if isinstance(positionOrRange, Position):
            self.range = Range(positionOrRange, positionOrRange)
        else:
            self.range = range
