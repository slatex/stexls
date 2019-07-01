from __future__ import annotations
from typing import Union
from ..misc.location import Location


class LinterException(Exception):
    pass


class LinterArgumentCountException(LinterException):
    @staticmethod
    def create(location: Location, expected: Union[int, str], found: int) -> LinterArgumentCountException:
        return LinterArgumentCountException(
            f'{location} Expected were {expected} argument(s) (found {found} argument(s))')


class LinterGimportModuleFormatException(LinterException):
    @staticmethod
    def create(location: Location, found: str) -> LinterGimportModuleFormatException:
        return LinterGimportModuleFormatException(f'{location} Invalid gimport argument "{found}":'
                                                  f' Expected format is "<base>/<repository>"')


class LinterModuleFromFilenameException(LinterException):
    @staticmethod
    def create() -> LinterModuleFromFilenameException:
        return LinterModuleFromFilenameException(
            f'Unable to extract module from file:'
            f'Expected filename format is .../<base>/<repository>/"source"/<module>')


class LinterDuplicateDefinitionException(LinterException):
    @staticmethod
    def create(identifier: str, new: Location, previous: Location) -> LinterDuplicateDefinitionException:
        return LinterDuplicateDefinitionException(
            f'{new} Duplicate definition of {identifier}: Previous definition here "{previous}"')


class LinterInternalException(LinterException):
    @staticmethod
    def create(file: str, message: str) -> LinterInternalException:
        return LinterInternalException(f'{file} Internal exception: {message}')
