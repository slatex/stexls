from __future__ import annotations

import os.path as _path
import json

class Position:
    def __init__(self, line: int, column: int):
        self.line = line
        self.column = column
    
    def __iter__(self):
        yield self.line
        yield self.column
    
    def __le__(self, that):
        return self.line < that.line or (self.line == that.line and self.column < that.column)
    
    def __eq__(self, that):
        return self.line == that.line and self.column == that.column
    
    def __ne__(self, that):
        return not (self == that)
    
    def to_json(self):
        return json.dumps(self.__dict__)
    
    def __hash__(self):
        return hash(self.line) ^ hash(self.column)
    
    def before(self, value, strict=False):
        """ Returns true if this position is before the given value. """
        return self.line < value.line or (self.line == value.line and (self.column < value.column or (not strict and self.column == value.column)))
    
    def after(self, value, strict=False):
        """ Returns true if this position is after the given value. """
        return value.line < self.line or (self.line == value.line and (value.column < self.column or (not strict and value.column == self.column)))
    
    def append_to_file(self, file):
        """ Appends the location to a file. """
        return f'{file}:{self.line}:{self.column}'
    
class Range:
    def __init__(self, begin: Position, end: Position):
        if not isinstance(begin, Position):
            raise ValueError("begin must be of type Position. Found: %s" % str(type(begin)))
        if not isinstance(end, Position):
            raise ValueError("end must be of type Position. Found: %s" % str(type(end)))
        self.begin = begin
        self.end = end
    
    def __eq__(self, that):
        return self.begin == that.begin and self.end == that.end
    
    def __ne__(self, that):
        return not (self == that)
    
    def before(self, value, strict=False):
        """ Returns True if this range is located before the given Position or Range. """
        if isinstance(value, Position):
            return self.end.before(value, strict=strict)
        # range
        return self.end.before(value.begin, strict=strict)
    
    def after(self, value, strict=False):
        """ Returns True if this range is located after the given Position or Range. """
        if isinstance(value, Position):
            return self.begin.after(value, strict=strict)
        # range
        return self.begin.after(value.end, strict=strict)
    
    def contains(self, value, strict=False):
        """ Returns True if the value of type Position or Range is contained in this range. """
        if isinstance(value, Position):
            return self.begin.before(value, strict=strict) and self.end.after(value, strict=strict)
        # range
        return self.begin.before(value.begin, strict=strict) and self.end.after(value.end, strict=strict)
    
    def to_json(self):
        return json.dumps(self, default=lambda obj: obj.__dict__)
    
    def __hash__(self):
        return hash(self.begin) ^ hash(self.end)
    
    def append_to_file(self, file, use_end=False):
        """ Appends the begin or end position of the range to a file. """
        if use_end:
            return self.end.append_to_file(file)
        else:
            return self.begin.append_to_file(file)
    
    def __iter__(self):
        yield self.begin
        yield self.end

class Location:
    def __init__(self, file: str, range: Range, offset: tuple = None):
        """ Creates a range in a file.
        Arguments:
            :param file: The target file.
            :param range: The range in the file.
            :param offset: Optional precomputed character offset representation for the range: tuple(begin, end). If None then the offset will be computed by loading the file.
        """
        self.file = _path.abspath(file)
        self.range = range
        self._offset = offset
        self._text = None
    
    @property
    def offset(self):
        """ Returns the range as a character offset tuple (begin:int, end:int) """
        if self._offset is not None:
            return self._offset
        with open(self.file) as ref:
            lines = ref.read().split('\n')
            self._offset = (
                sum(map(len, lines[:self.range.begin.line - 1])) + self.range.begin.line - 1 + self.range.begin.column - 1,
                sum(map(len, lines[:self.range.end.line - 1])) + self.range.end.line - 1 + self.range.end.column - 1
            )
        return self._offset
    
    @property
    def text(self):
        """ Returns the string in the range by opening the file. """
        if self._text is not None:
            return self._text
        begin, end = self.offset
        with open(self.file) as ref:
            self._text = ref.read()[begin:end]
        return self._text
    
    def to_json(self):
        return f'{{"file":"{self.file}","range":{self.range.to_json()}}}'
    
    def to_string(self):
        return self.to_link()
    
    def to_link(self):
        return self.range.begin.append_to_file(self.file)
    
    def __repr__(self):
        return self.to_string()
    
    @property
    def relative(self):
        l = Location(self.file, self.range, self._offset)
        l._text = self._text
        l.file = _path.relpath(self.file)
        return l
    
    def __eq__(self, that):
        return _path.abspath(self.file) == _path.abspath(that.file) and self.range == that.range
    
    def __ne__(self, that):
        return not (self == that)
    
    def __hash__(self):
        return hash(_path.abspath(self.file)) ^ hash(self.range)
