__all__ = ['CompilerException', 'CompilerWarning']

class CompilerException(Exception):
    pass


class CompilerWarning(CompilerException, Warning):
    pass
