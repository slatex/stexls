
class NotCompiledError(Exception):
    pass

# TODO: Maybe a seperate exceptions module is not needed and the module that creates their respective exception should declare the needed exceptions in their module?

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


class DuplicateSymbolDefinedException(CompilerError):
    pass


class InvalidSymbolRedifinitionException(CompilerError):
    pass
