__all__ = ['CompilerError', 'CompilerWarning', 'LinkError', 'LinkWarning']

class CompilerError(Exception):
    pass


class CompilerWarning(CompilerError, Warning):
    pass


class LinkError(Exception):
    pass


class LinkWarning(LinkError, Warning):
    pass
