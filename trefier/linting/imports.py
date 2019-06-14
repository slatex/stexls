from __future__ import annotations
from typing import List, Dict, Tuple, Optional, Set
import numpy as np
import subprocess
import sys
import tempfile
from PIL import Image

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

        # dict from modules to a list of transitively imported modules
        self.transitive: Dict[str, Set[str]] = dict()

        # Dict[Module, Dict[Imported Module, (Direct Import Location, Transitive Import Location)]]
        # The Transitive import location should have precedence and the direct import location should be removed
        self.redundant: Dict[str, Dict[str, Tuple[Location, Location]]] = dict()

        # dict of modules to imports with the list of other modules that are part of the cycle?
        self.cycles: Dict[str, Dict[Location, List[str]]] = dict()

    def add(self, document: Document):
        document_module = str(document.module_identifier)
        if document_module in self.modules:
            raise LinterInternalException.create(
                document.module,
                f'Attempted to add duplicate definition of module "{document_module}" to import graph:'
                f' Previous definition in "{self.modules[document_module]}"')

        self.modules[document_module] = document.file
        self.graph[document_module] = dict()
        self.duplicates[document_module] = dict()
        self.references.setdefault(document_module, {})
        self.transitive[document_module] = set()
        self.redundant[document_module] = dict()
        self.cycles[document_module] = dict()

        # mark module as resolved to parents
        if document_module in self.unresolved:
            for resolved, location in self.unresolved[document_module].items():
                self.references[document_module][resolved] = location
            del self.unresolved[document_module]

        for gimport in document.gimports:
            imported_module = str(gimport.imported_module)
            if imported_module in self.graph[document_module]:
                self.duplicates[document_module].setdefault(imported_module, [])
                self.duplicates[document_module][imported_module].append(gimport)
            else:
                # register in graph
                self.graph[document_module][imported_module] = gimport
                if imported_module not in self.graph:
                    # register as unresolved if imported module is not in graph
                    self.unresolved.setdefault(imported_module, {})
                    self.unresolved[imported_module][document_module] = gimport
                else:
                    # else add back reference
                    self.references.setdefault(imported_module, {})
                    self.references[imported_module][document_module] = gimport

    def remove(self, module: ModuleIdentifier):
        module = str(module)
        if module not in self.modules:
            raise LinterInternalException.create(
                module, f'Can\'t remove module from import graph: Module not tracked')

        for imported_module in self.graph[module]:
            if imported_module in self.references:
                # remove back references from children
                del self.references[imported_module][module]
                if not self.references[imported_module]:
                    del self.references[imported_module]
            elif imported_module in self.unresolved:
                # remove the unresolved instanced created by this module
                del self.unresolved[imported_module][module]
                if not self.unresolved[imported_module]:
                    del self.unresolved[imported_module]

        # add this to unresolved references of a parent
        for parent_module, location in self.references.get(module, {}).items():
            # only if parent was not also deleted
            if parent_module in self.graph:
                self.unresolved.setdefault(module, {})
                self.unresolved[module][parent_module] = location

        # delete other information
        del self.modules[module]
        del self.graph[module]
        del self.duplicates[module]
        del self.cycles[module]
        del self.transitive[module]
        del self.redundant[module]

    def get_info(self, module: ModuleIdentifier):
        module = str(module)
        return {
            'file': self.modules.get(module),
            'imports': self.graph.get(module),
            'duplicates': self.duplicates.get(module),
            'transitive': self.transitive.get(module),
            'redundant': self.redundant.get(module),
            'unresolved': self.unresolved.get(module),
            'references': self.references.get(module),
        }
    
    def get_reverse_info(self, module: ModuleIdentifier):
        module = str(module)
        return {
            'file': self.modules.get(module),
            'imports': [other for other, imports in self.graph.items() if module in imports],
            'transitive': [other for other, modules in self.transitive.items() if module in modules],
            'unresolved': [other for other, u in self.unresolved.items() if module in u]
        }

    def write_image(self,
              root: ModuleIdentifier,
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
                    elif imported_module in self.transitive[current]:
                        color = 'red'

                    dot.add_edge(pydot.Edge(current, imported_module, color=color, style=style))

        dot.write_png(path)
        return path

    def open_in_image_viewer(self,
                             root: ModuleIdentifier,
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
