from typing import Iterable


__all__ = ('format_enumeration',)


def format_enumeration(it: Iterable[str], last: str = 'and'):
    ''' Formats an enumeration into a comma concatenated list except for the last two elements, which are concatenated with "and" or "or"

    >>> format_enumeration([])
    ''
    >>> format_enumeration(['single'])
    '"single"'
    >>> format_enumeration(['element1', 'element2'])
    '"element1" and "element2"'
    >>> format_enumeration(['element1', 'element2', 'element3'])
    '"element1", "element2" and "element3"'
    >>> format_enumeration(['element1', 'element2', 'element3'], last='or')
    '"element1", "element2" or "element3"'
    '''
    l = list(it)
    if not l:
        return ''
    if len(l) > 1:
        s = (f'" {last} "').join(('", "'.join(l[:-1]), l[-1]))
    else:
        s = l[0]
    return '"' + s + '"'
