
_ROMAN_NUMERALS = ('i', 'ii', 'iii', 'iv', 'v', 'vi',
                   'vii', 'viii', 'ix', 'x', 'xi', 'xii')


def int2roman(i: int) -> str:
    return _ROMAN_NUMERALS[i - 1]


def roman2int(r: str) -> int:
    return _ROMAN_NUMERALS.index(r) + 1
