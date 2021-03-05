import random
import string

__all__ = ['create_random_string']


def create_random_string(size: int) -> str:
    ' Creates a random ascii string of given size @size. '
    return ''.join(random.choices(string.ascii_letters, k=size))
