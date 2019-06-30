from __future__ import annotations
from typing import List, Dict, Tuple, Optional, Set
import numpy as np
import subprocess
import sys
import tempfile

from .exceptions import *
from .identifiers import *
from .document import Document

__all__ = ['ImportGraph']


class ImportGraph:
    def __init__(self):
        # dict of modules to the file that added it to the graph
        self.modules: Dict[str, str] = dict()

        # dict of modules to modules it imports and where it imports them
        self.graph: Dict[str, Dict[str, Location]] = dict()

        # dict of modules to an imported module and the list to duplicate import locations
        self.duplicates: Dict[str, Dict[str, List[Location]]] = dict()

        # dict of back-references: Dict[imported module, Dict[module, location]]
        self.references: Dict[str, Dict[str, Location]] = dict()

        # dict from unresolved imported modules to the module and location where it was imported from
        self.unresolved: Dict[str, Dict[str, Location]] = dict()

        # dict from module to modules that are transitively imported
        self.transitive: Dict[str, Dict[str, List[str]]] = dict()

        # dict from module to modules that are directly imported but also indirectly
        self.redundant: Dict[str, Dict[str, List[str]]] = dict()

        # dict from module to import that causes a cycle
        self.cycles: Dict[str, Dict[str, List[str]]] = dict()

        # log of modules that changed: cleared on update
        self._changed: Set[str] = set()

    def update(self, force_update: Optional[Set[Union[ModuleIdentifier, str]]] = None) -> Set[str]:
        """ Needs to be called after all modules have been added or removed. This is a kind of linker, that
            uses the imports of all modules to find transitive, redundant and cyclical imports.
            :param force_update: Set of modules that the user wants to force mark updated
            :returns set of changed modules """
        # mark all parents of all nodes that have been changed as changed as well
        frontier = self._changed | set(map(str, force_update or ()))
        self._changed.clear()
        need_update = set()
        while frontier:
            current = frontier.pop()
            need_update.add(current)
            if current in self.unresolved:
                continue
            for parent in self.references.get(current, ()):
                if parent not in need_update:
                    frontier.add(parent)

        # remove unresolved from update
        need_update -= set(self.unresolved)

        # delete old information
        for current in need_update:
            if current in self.transitive:
                del self.transitive[current]
                del self.redundant[current]
                del self.cycles[current]

        # reduce new information
        for current in need_update:
            if current in self.graph:
                self._reduce_transitive(current, [])
        
        return need_update

    def add(self, document: Document):
        """ Adds a module to the graph. """
        assert document is not None
        assert document.module is not None
        document_module = str(document.module_identifier)
        if document_module in self.modules:
            raise LinterInternalException.create(
                document.module,
                f'Attempted to add duplicate definition of module "{document_module}" to import graph:'
                f' Previous definition in "{self.modules[document_module]}"')
        
        self._changed.add(document_module)
        self.modules[document_module] = document.file
        self.graph[document_module] = dict()
        self.duplicates[document_module] = dict()
        self.references[document_module] = dict()

        assert document_module not in self.transitive
        assert document_module not in self.redundant
        assert document_module not in self.cycles

        # mark module as resolved to parents
        if document_module in self.unresolved:
            for resolved, location in self.unresolved[document_module].items():
                self.references[document_module][resolved] = location
            # remove from unresolved list
            del self.unresolved[document_module]

        for gimport in document.gimports:
            imported_module = str(gimport.imported_module)
            if imported_module in self.graph[document_module]:
                self.duplicates[document_module].setdefault(imported_module, [])
                self.duplicates[document_module][imported_module].append(gimport)
            else:
                if imported_module in self.graph:
                    # add back reference
                    assert imported_module in self.references
                    assert document_module not in self.references[imported_module]
                    self.references[imported_module][document_module] = gimport
                else:
                    # mark unresolved if imported module is not in graph
                    self.unresolved.setdefault(imported_module, {})
                    assert document_module not in self.unresolved[imported_module]
                    self.unresolved[imported_module][document_module] = gimport
                # register self in graph
                self.graph[document_module][imported_module] = gimport

    def remove(self, module: ModuleIdentifier):
        """ Removes a module and its associated information from the graph. """
        module = str(module)
        if module not in self.modules:
            raise LinterInternalException.create(
                module, f'Can\'t remove module from import graph: Module not tracked')

        for imported_module in self.graph[module]:
            if imported_module in self.references:
                # remove back references from children
                del self.references[imported_module][module]
            elif imported_module in self.unresolved:
                # remove the unresolved instanced created by this module
                del self.unresolved[imported_module][module]
                if not self.unresolved[imported_module]:
                    del self.unresolved[imported_module]

        # add this to unresolved references of a parent
        for parent_module, location in self.references.get(module, {}).items():
            # only if parent was not also deleted
            if parent_module in self.graph:
                self._changed.add(parent_module)
                self.unresolved.setdefault(module, {})
                self.unresolved[module][parent_module] = location

        # delete other information
        if module in self._changed:
            self._changed.remove(module)
        del self.references[module]
        del self.modules[module]
        del self.graph[module]
        del self.duplicates[module]
        del self.transitive[module]
        del self.redundant[module]
        del self.cycles[module]

    def reachable_modules_of(self, module: Union[ModuleIdentifier, str]) -> Set[str]:
        """ Returns set of all modules that are directly or indirectly imported as well as the current module. """
        return (
                {str(module)}
                | set(self.transitive.get(str(module), {}))
                | set(self.graph.get(str(module), {})))

    def parents_of(self, module: Union[ModuleIdentifier, str]) -> Set[str]:
        """ Returns set of all parents that reference this module directly or indirectly. """
        visited = set()
        frontier = {str(module)}
        while frontier:
            current = frontier.pop()
            visited.add(current)
            for reference in self.references[current]:
                if reference not in visited:
                    frontier.add(reference)
        return visited

    def write_image(self,
              root: Union[ModuleIdentifier, str],
              path: str = None) -> Tuple[str, np.ndarray]:
        import pydot
        dot = pydot.Dot(graph_type='digraph')
        queue = {str(root)}
        visited = set()
        while queue:
            current = queue.pop()
            visited.add(current)
            imports = self.graph.get(current)
            if imports is None:
                dot.add_node(pydot.Node(current, color='red'))
            else:
                dot.add_node(pydot.Node(current))
                for imported_module in imports:
                    if imported_module not in visited:
                        queue.add(imported_module)

                    color = 'black'
                    style = 'solid'
                    if imported_module in self.unresolved:
                        color = 'red'
                        style = 'dotted'
                    elif imported_module in self.redundant[current]:
                        color = 'red'
                    elif imported_module in self.cycles[current]:
                        color = 'green'

                    dot.add_edge(pydot.Edge(current, imported_module, color=color, style=style))

        dot.write_png(path)
        return path

    def open_in_image_viewer(self,
                             root: Union[ModuleIdentifier, str],
                             path: Optional[str] = None,
                             image_viewer: Optional[str] = None) -> str:
        """ Renders the graph to a tempfile, then opens it in the default image viewer of the computer.

        Arguments:
            :param path: If set, uses this image instead of rendering it to a new tempfile first
            :param image_viewer: Optional image viewer. Default image viewer is used if 'None'.
        """
        image_viewer = image_viewer or {'linux': 'xdg-open', 'win32': 'explorer', 'darwin': 'open'}[sys.platform]
        if path is None:
            with tempfile.NamedTemporaryFile(delete=False, prefix='trefier.graph.', suffix='.png') as file:
                self.write_image(root, file.name)
                file.flush()
                path = file.name
        subprocess.run([image_viewer, path])
        return path

    def _reduce_transitive(
            self,
            current: Union[ModuleIdentifier, str],
            stack: List[Union[ModuleIdentifier, str]]) -> Set[str]:
        # return empty transitive set if unresolved
        if current in self.unresolved:
            return set()

        stack.append(current)

        # update transitive, redundant and cycle information if not up to date
        if current not in self.transitive:
            self.transitive[current] = {}
            self.redundant[current] = {}
            self.cycles[current] = {}

            # gather transitive import information
            for child, location in self.graph[current].items():
                if child in stack:
                    # transitive array always empty if accessing something on the stack
                    # mark cycle
                    self.cycles[current].setdefault(child, [])
                    self.cycles[current][child].append(child)
                for transitive_child in self._reduce_transitive(child, stack):
                    if transitive_child == current:
                        # transitive import is self -> cycle
                        self.cycles[current].setdefault(child, [])
                        self.cycles[current][child].append(child)
                    elif transitive_child in self.graph[current]:
                        # transitive import is in direct imports -> redundant import
                        self.redundant[current].setdefault(transitive_child, [])
                        self.redundant[current][transitive_child].append(child)
                    else:
                        # else register as transitive
                        self.transitive[current].setdefault(transitive_child, [])
                        self.transitive[current][transitive_child].append(child)

        popped = stack.pop()
        assert current == popped, "Stack resolution failed"

        # return transitive with respect to the caller
        # => current transitive imports + direct imports
        return set(self.transitive[current]) | set(self.graph[current])
