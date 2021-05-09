
from typing import Optional


class ProgressInterface:
    def __init__(self, length: Optional[int] = None, title: Optional[str] = None) -> None:
        self.length: Optional[int] = length
        self.title: Optional[str] = title
        self.index: int = 0

    @property
    def percentage(self) -> Optional[int]:
        if self.length is None:
            return None
        if self.length <= 0:
            return 100
        return int(round(100 * self.index / self.length))

    @property
    def progress_string(self) -> str:
        title = f'{self.title}: ' if self.title else ''
        if self.length is None:
            return f'{title}{self.index}/?'
        return f'{title}{self.percentage}% ({self.index}/{self.length})'

    def update(
            self,
            index: Optional[int] = None,
            length: Optional[int] = None,
            title: Optional[str] = None
    ):
        if index is None:
            self.index += 1
        else:
            self.index = index
        if length is not None:
            self.length = length
        if title is not None:
            self.title = title
        self.publish()

    def publish(self):
        pass

    def __len__(self):
        return self.length

    @classmethod
    def from_iter(cls, it, title: Optional[str] = None, *args, **kwargs):
        if hasattr(it, "__len__"):
            prog = cls(*args, length=len(it), title=title, **kwargs)
        else:
            prog = cls(title=title, **kwargs)
        prog.publish()
        for i, el in enumerate(it):
            yield el
            prog.update(i + 1)
