from typing import Union, Optional, List

__all__ = ['ByteBuffer']

class ByteBuffer:
    def __init__(self):
        self.buffer = b''
    
    def append(self, data: Union[str, bytes]):
        if isinstance(data, str):
            data = bytes(data, 'utf-8')
        self.buffer += data
    
    def has_line(self) -> Optional[str]:
        return b'\n' in self.buffer

    def readln(self) -> Optional[str]:
        if self.has_line():
            ln, self.buffer = self.buffer.split(b'\n', maxsplit=1)
            return ln.decode('utf-8')
        return None
    
    def readlines(self) -> List[str]:
        if self.has_line():
            *lines, self.buffer = self.buffer.split(b'\n')
            return [
                ln.decode('utf-8')
                for ln in lines
            ]
        return []
    
    def size(self) -> int:
        return len(self.buffer)
    
    def readbytes(self, count: int) -> bytes:
        data = self.buffer[:count]
        self.buffer = self.buffer[count:]
        return data