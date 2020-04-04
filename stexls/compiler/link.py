""" Linker for stex objects.
"""
from typing import List, Dict, Tuple, Set
from pathlib import Path
from itertools import chain
import os
import multiprocessing
from stexls.util.location import Location
from stexls.util.file_watcher import WorkspaceWatcher
from .parse import parse
from .compile import StexObject
from .exceptions import *

__all__ = ['Linker']

class Linker:
    def __init__(self, root: str, limit: int = None):
        self.limit = limit
        self.root = root
        self.watcher = WorkspaceWatcher(os.path.join(root, '**/*.tex'))
        self.objects: Dict[Path, List[StexObject]] = {}
        self.module_index: Dict[Path, Dict[str, StexObject]] = {}
        self.build_orders: Dict[StexObject, Tuple[List[StexObject], List[Location]]] = {}
        self.links: Dict[StexObject, StexObject] = {}
        self.changes = None

    @staticmethod
    def _compile(*args, **kwargs):
        return list(StexObject.compile(*args, **kwargs))

    @staticmethod
    def _link(objects: List[StexObject]) -> StexObject:
        linked = StexObject()
        for object in objects:
            linked.link(object, object == objects[-1])
        return linked

    @staticmethod
    def _make_build_order(
        root: StexObject,
        index: Dict[Path, Dict[str, StexObject]],
        location: Location = None,
        cache: Dict[StexObject, Tuple[List[StexObject], List[Location]]] = None,
        import_private: bool = True,
        visited: Dict[StexObject, Location] = None) -> List[StexObject]:
        visited = dict() if visited is None else visited
        cache = dict() if cache is None else cache
        if root not in cache:
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
                            raise LinkError(f'{location.format_link()}: Cyclic dependency "{module}" imported at "{visited[object].format_link()}"')
                        visited2 = visited.copy() # copy to emulate depth first search
                        visited2[object] = location
                        subobjects = Linker._make_build_order(object, index, location=location, cache=cache, import_private=False, visited=visited2)
                        for subobject in subobjects:
                            if subobject in objects:
                                objects.remove(subobject)
                                break
                        objects = subobjects + objects
            assert root not in cache
            cache[root] = (objects + [root], [])
        if location:
            cache[root][1].append(location)
        return cache[root][0]

    def _gather_removed_files(self) -> Set[Path]:
        return set(self.changes.deleted)

    def _gather_changed_files(self) -> Set[Path]:
        return set(list(self.changes.created | self.changes.modified)[:self.limit])

    def _gather_removed_objects(
        self,
        removed_files: Set[Path]) -> Set[StexObject]:
        return set(
            object
            for file
            in removed_files
            for object in self.objects.get(file, ()))

    def _gather_changed_objects(
        self,
        changed_files: Set[Path]) -> Set[StexObject]:
        return set(
            object
            for file in changed_files
            for object in self.objects.get(file, ()))

    def _gather_changed_build_orders(
        self,
        changed_objects: Set[StexObject],
        removed_objects: Set[StexObject]) -> Set[StexObject]:
        return set(
            object
            for parent
            in chain(changed_objects, removed_objects)
            for object, (order, _) in self.build_orders.items()
            if object not in removed_objects
            and parent in order)

    def _cleanup(
        self,
        removed_files: Set[Path],
        changed_files: Set[Path],
        removed_objects: Set[StexObject],
        changed_objects: Set[StexObject],
        changed_build_orders: Set[StexObject]):
        for path in (removed_files | changed_files):
            if path in self.objects:
                del self.objects[path]
            if path in self.module_index:
                del self.module_index[path]
            if path in self.links:
                del self.links[path]
        for object in (removed_objects | changed_objects):
            if object in self.build_orders:
                del self.build_orders[object]
        for object in (removed_objects | changed_build_orders):
            if object in self.links:
                del self.links[object]
    
    def update(self, progress=None, use_multiprocessing: bool = True):
        progress = progress or (lambda x: x)
        self.changes = self.watcher.update()
        changed_files = self._gather_changed_files()
        removed_files = self._gather_removed_files()
        removed_objects = self._gather_removed_objects(removed_files)
        changed_objects = self._gather_changed_objects(changed_files)
        changed_build_orders = self._gather_changed_build_orders(changed_objects, removed_objects)
        self._cleanup(
            removed_files,
            changed_files,
            removed_objects,
            changed_objects,
            changed_build_orders)
        with multiprocessing.Pool() as pool:
            mapfn = pool.map if use_multiprocessing else map

            parsed = {
                file: parsed
                for file, parsed
                in zip(
                    changed_files,
                    mapfn(parse, progress(changed_files))
                )
                if parsed
            }

            compiled = {
                file: objects
                for file, objects
                in zip(
                    parsed.keys(),
                    mapfn(Linker._compile, progress(parsed.values()))
                )
                if objects
            }

        for path, objects in compiled.items():
            for object in objects:
                if object.module:
                    self.module_index.setdefault(path, dict())[object.module] = object
        
        changed_links = set(object for objects in compiled.values() for object in objects) | changed_build_orders
        errors = {}
        for object in progress(changed_links):
            try:
                order = Linker._make_build_order(object, self.module_index, cache=self.build_orders)
                link = Linker._link(order)
                self.links[object] = link
            except (CompilerError, LinkError) as e:
                errors[object] = e
        self.objects.update(compiled)
        return errors
