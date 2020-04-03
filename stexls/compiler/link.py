""" Linker for stex objects.
"""
from typing import List, Dict, Tuple, Set
from pathlib import Path
from itertools import chain
from stexls.util.location import Location
from .compile import StexObject
from .symbols import AccessModifier
from .exceptions import LinkException

__all__ = ['make_build_order', 'link']

def make_build_order(root: StexObject, index: Dict[Path, Dict[str, StexObject]], import_private: bool = True, visited: Dict[StexObject, Location] = None) -> List[StexObject]:
    visited = visited or dict()
    objects = []
    for module, files in root.dependencies.items():
        for path, locations in files.items():
            if path not in index:
                for loc in locations:
                    print(f'{loc.format_link()}: File not indexed:"{path}"')
                continue
            object = index[path].get(module)
            if not object:
                print(f'Undefined module: "{module}" not defined in "{path}"')
                continue
            for location, public in locations.items():
                if not import_private and not public:
                    continue # skip private imports
                if object in visited:
                    raise LinkException(f'{location.format_link()}: Cyclic dependency "{module}" imported at "{visited[object].format_link()}"')
                visited2 = visited.copy() # copy to emulate depth first search
                visited2[object] = location
                subobjects = make_build_order(object, index, import_private=False, visited=visited2)
                for sub in subobjects:
                    if sub in objects:
                        objects.remove(sub)
                objects = subobjects + objects
                break # only import the first location with proper access rights
    return objects + [root]

def link(objects: List[StexObject]) -> StexObject:
    return
