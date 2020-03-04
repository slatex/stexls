from __future__ import annotations
from typing import List, Dict, Hashable, Set

from stexls.util.location import Location

__all__ = ['ImportGraph']


class ImportGraph:
    def __init__(self):
        # dict of modules to the file that added it to the graph
        self.modules: Dict[Hashable, Hashable] = dict()

        # dict of modules to modules it imports and where it imports them
        self.graph: Dict[Hashable, Dict[Hashable, Location]] = dict()

        # dict of modules to an imported module and the list to duplicate import locations
        self.duplicates: Dict[Hashable, Dict[Hashable, List[Location]]] = dict()

        # dict of back-references: Dict[imported module, Dict[module, location]]
        self.references: Dict[Hashable, Dict[Hashable, Location]] = dict()

        # dict from unresolved imported modules to the module and location where it was imported from
        self.unresolved: Dict[Hashable, Dict[Hashable, Location]] = dict()

        # dict from module to modules that are transitively imported
        self.transitive: Dict[Hashable, Dict[Hashable, List[Hashable]]] = dict()

        # dict from module to modules that are directly imported but also indirectly
        self.redundant: Dict[Hashable, Dict[Hashable, List[Hashable]]] = dict()

        # dict from module to import that causes a cycle
        self.cycles: Dict[Hashable, Dict[Hashable, List[Hashable]]] = dict()

    def add(self, node: Hashable, edges: Set[Hashable]):
        pass

    def remove(self, node: Hashable):
        pass
    
    def update(self):
        pass
