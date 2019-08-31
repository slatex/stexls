from typing import Optional

_ROMAN_NUMERALS = ('i', 'ii', 'iii', 'iv', 'v', 'vi', 'vii', 'viii', 'ix', 'x', 'xi', 'xii')

def int2roman(i: int) -> Optional[str]:
    try:
        return _ROMAN_NUMERALS[i - 1]
    except:
        return None

def roman2int(r: str) -> Optional[int]:
    try:
        return _ROMAN_NUMERALS.index(r) + 1
    except:
        return None
