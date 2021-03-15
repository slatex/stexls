from stexls.vscode import Location


class NotCompiledError(Exception):
    pass

# TODO: Maybe a seperate exceptions module is not needed and the module
# that creates their respective exception should declare the needed exceptions in their module?


class CompilerError(Exception):
    pass


class CompilerWarning(CompilerError, Warning):
    pass


class LinkError(Exception):
    pass


class LinkWarning(LinkError, Warning):
    pass


class Info(Exception):
    pass


class DuplicateSymbolDefinedError(CompilerError):
    def __init__(self, name: str, previous_location: Location):
        super().__init__(
            f'Duplicate definition of {name}: Previously defined at {previous_location.format_link()}')
        self.name = name
        self.previous_location = previous_location


class InvalidSymbolRedifinitionException(CompilerError):
    def __init__(self, name: str, other_location: Location, info: str):
        super().__init__(
            f'Invalid redefinition of {name} at {other_location.format_link()}: {info}')
        self.name = name
        self.other_location = other_location
        self.info = info
