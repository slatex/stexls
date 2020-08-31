
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
