from __future__ import annotations

__all__ = [
    'LinterException',
    'ArgumentCountException',
    'InternalException'
]


class LinterException(Exception):
    pass


class ArgumentCountException(LinterException):
    @staticmethod
    def create(expected, found) -> ArgumentCountException:
        return ArgumentCountException(
            f'Expected were {expected} argument(s) (found {found} argument(s))')


class InternalException(LinterException):
    @staticmethod
    def create(message: str) -> InternalException:
        return InternalException(message)
