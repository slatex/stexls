from typing import TypeVar, Optional


NotNoneType = TypeVar('NotNoneType')


def unwrap(option: Optional[NotNoneType]) -> NotNoneType:
    ' Asserts that input is not None then returns the input. '
    assert option is not None
    return option


__all__ = ['unwrap']
