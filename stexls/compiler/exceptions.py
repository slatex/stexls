__all__ = ['CompilerException', 'CompilerWarning', 'LinkException']

class CompilerException(Exception):
    pass


class CompilerWarning(CompilerException, Warning):
    pass


class LinkException(Exception):
    pass
