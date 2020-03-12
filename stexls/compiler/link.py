""" Linker for stex objects.
"""
from typing import List
from stexls.compiler.objects import StexObject

__all__ = ['link']

def link(objects: List[StexObject]):
    dependencies = _build_dependencies(objects)
    dependencies = _order_dependencies(dependencies)

def _build_dependencies(objects: List[StexObject]):
    pass

def _order_dependencies(dependencies):
    return dependencies
