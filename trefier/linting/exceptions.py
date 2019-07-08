from __future__ import annotations
from typing import Union
from ..misc.location import Location


class LinterException(Exception):
    pass


class LinterArgumentCountException(LinterException):
    @staticmethod
    def create(expected: Union[int, str], found: int) -> LinterArgumentCountException:
        return LinterArgumentCountException(
            f'Expected were {expected} argument(s) (found {found} argument(s))')


class LinterModuleFromFilenameException(LinterException):
    @staticmethod
    def create() -> LinterModuleFromFilenameException:
        return LinterModuleFromFilenameException(
            f'Unable to extract module from file:'
            f'Expected filename format is .../<base>/<repository>/"source"/<module>')


class LinterInternalException(LinterException):
    @staticmethod
    def create(message: str) -> LinterInternalException:
        return LinterInternalException(f'Internal exception: {message}')
