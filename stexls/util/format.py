from typing import Iterable

__all__ = ['format_enumeration']


# TODO: Find better place for this function
def format_enumeration(it: Iterable[str], last: str = 'and', add_quotes: bool = True):
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
    quotesO = '" ' if add_quotes else ''
    quotesC = ' "' if add_quotes else ''
    quotesN = '"' if add_quotes else ''
    items = list(it)
    if not items:
        return ''
    if len(items) > 1:
        s = (f'{quotesO}{last}{quotesC}').join(
            (f'{quotesN}, {quotesN}'.join(items[:-1]), items[-1]))
    else:
        s = items[0]
    return quotesN + s + quotesN
