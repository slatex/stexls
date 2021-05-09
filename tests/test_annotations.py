from pathlib import Path
from typing import Dict, List, Literal, Optional, Tuple, Union
from unittest import TestCase

from stexls import vscode
from stexls.jsonrpc.annotations import JsonToPyFromAnnotationConstructor


class TestAnnotations(TestCase):
    def test_union(self):
        ctor = JsonToPyFromAnnotationConstructor(Union[float, str])
        self.assertIsInstance(ctor('string'), str)
        self.assertIsInstance(ctor(-0.1), float)
        self.assertIsInstance(ctor(1.0), float)

    def test_dict(self):
        ctor = JsonToPyFromAnnotationConstructor(
            Dict[Union[float, str], Optional[Tuple[str, ...]]])
        json = {1.0: ('a', 'b'), 'string': None}
        self.assertDictEqual(ctor(json), json)
        self.assertRaises(Exception, ctor, {(1, 2): (3, 4)})

    def test_vscode(self):
        file_uri = Path('some/file.tex').absolute().as_uri()
        start = vscode.Position(1, 2)
        stop = vscode.Position(3, 4)
        loc = vscode.Location(file_uri, vscode.Range(start, stop))
        json = loc.to_json()
        ctor = JsonToPyFromAnnotationConstructor(vscode.Location)
        self.assertIsInstance(ctor(json), vscode.Location)
        self.assertDictEqual(ctor(json).to_json(), json)

    def test_compound_vscode(self):
        file_uri = Path('some/file.tex').absolute().as_uri()
        start = vscode.Position(1, 2)
        stop = vscode.Position(3, 4)
        loc = vscode.Location(file_uri, vscode.Range(start, stop)).to_json()
        ctor = JsonToPyFromAnnotationConstructor(
            Optional[List[vscode.Location]])
        self.assertIsInstance(ctor(None), type(None))
        self.assertIsInstance(ctor((loc, loc)), list)
        self.assertDictEqual(ctor((loc, loc))[0].to_json(), loc)

    def test_option(self):
        octor = JsonToPyFromAnnotationConstructor(
            Optional[Union[int, float, str]])
        self.assertIs(octor(None), None)
        self.assertIsInstance(octor(1), int)
        self.assertIsInstance(octor(1.5), float)
        self.assertIsInstance(octor('str'), str)
        self.assertRaises(ValueError, octor, (1, 2, 3))
        ctor = JsonToPyFromAnnotationConstructor(Union[int, str])
        self.assertRaises(ValueError, ctor, None)
        self.assertIsInstance(ctor(1), int)
        self.assertIsInstance(ctor(1.0), float)
        self.assertIsInstance(ctor('str'), str)

    def test_tuple(self):
        ctor = JsonToPyFromAnnotationConstructor(
            Dict[str, Tuple[vscode.Position, vscode.Location]])
        start = vscode.Position(1, 2)
        stop = vscode.Position(3, 4)
        range = vscode.Range(start, stop)
        uri = Path('some/file.tex').absolute().as_uri()
        location = vscode.Location(uri, range)
        json = {'x': (start.to_json(), location.to_json())}
        reconstructed = ctor(json)
        self.assertIsInstance(reconstructed['x'], tuple)
        self.assertIsInstance(reconstructed['x'][0], vscode.Position)
        self.assertIsInstance(reconstructed['x'][1], vscode.Location)
        json2 = {'x': start.to_json()}
        self.assertRaises(Exception, ctor, json2)

    def test_fail_none(self):
        ctor = JsonToPyFromAnnotationConstructor(int)
        self.assertRaises(Exception, ctor, None)

    def test_literal(self):
        ctor = JsonToPyFromAnnotationConstructor(
            Union[Literal[None, 1, 2, 'string'], vscode.Position])
        self.assertIs(ctor(None), None)
        self.assertEqual(ctor(1), 1)
        self.assertEqual(ctor(2), 2)
        self.assertEqual(ctor('string'), 'string')
        pos = vscode.Position(1, 2).to_json()
        self.assertIsInstance(ctor(pos), vscode.Position)
        self.assertDictEqual(ctor(pos).to_json(), pos)
        self.assertRaises(ValueError, ctor, 0)
        self.assertRaises(ValueError, ctor, 3)
        self.assertRaises(ValueError, ctor, 'other string')
