__all__ = ['CompilerException', 'CompilerWarning', 'LinkError', 'LinkWarning']

class CompilerException(Exception):
    pass


class CompilerWarning(CompilerException, Warning):
    pass


class LinkError(Exception):
    pass


class LinkWarning(LinkError, Warning):
    pass
