""" Linker for stex objects.
"""
import logging
from typing import List, Dict
from pathlib import Path
from stexls.util.location import Location
from .compile import StexObject

log = logging.getLogger(__name__)

__all__ = ['link', 'build_dependency_tree']

def build_dependency_tree(root: Path, index: Dict[Path, StexObject], location : Location = None) -> List[StexObject]:
    if root not in index:
        log.error('%s - Missing imported file "%s"', location.format_link(), root)
        return []
    root: StexObject = index[root]
    objects = []
    for path, locs in root.dependend_files.items():
        loc = list(locs)[0] if locs else None
        dep = build_dependency_tree(path, index, loc)
        objects = dep + objects
    return objects + [root]

def link(objects: List[StexObject]):
    obj = StexObject()
    for o in objects:
        duplicate = False
        for file in o.compiled_files:
            if file in obj.compiled_files:
                duplicate = True
        if duplicate:
            continue
        obj.errors.update(o.errors)
        for dep, locs in o.dependend_files.items():
            if dep not in obj.compiled_files:
                obj.dependend_files[dep].update(locs)
                for loc in locs:
                    log.error('%s - Missing dependency: %s', loc.format_link(), dep)
        for identifier, symbols in o.symbol_table.items():
            if identifier in obj.symbol_table:
                for current_symbol_def in obj.symbol_table[identifier]:
                    for previous_def_symbol in obj.symbol_table[identifier]:
                        log.error(
                            '%s - Duplicate definition of identifier %s'
                            ' previously defined at %s',
                            current_symbol_def.location.format_link(),
                            identifier,
                            previous_def_symbol.location.format_link())
            obj.symbol_table[identifier].extend(symbols)
        for file, references in o.references.items():
            for range, id in references.items():
                if id not in obj.symbol_table:
                    loc = Location(file, range)
                    log.warning('%s - Unresolved symbol: %s', loc.format_link(), id)
                obj.references[file][range] = id
        obj.compiled_files.update(o.compiled_files)
    return obj
