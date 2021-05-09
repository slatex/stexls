from typing import List
from unittest import TestCase


from stexls.util.progress_interface import ProgressInterface


class MockInterface(ProgressInterface):
    def __init__(self, test_case: TestCase, expected_outputs: List[str], *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.test_case = test_case
        self.expected_outputs = expected_outputs

    def publish(self):
        self.test_case.assertEqual(
            self.expected_outputs[self.index], self.progress_string)


class TestProgress(TestCase):
    def test_title(self):
        lst = MockInterface.from_iter(range(10), title='test title', test_case=self, expected_outputs=[
            'test title: 0% (0/10)',
            'test title: 10% (1/10)',
            'test title: 20% (2/10)',
            'test title: 30% (3/10)',
            'test title: 40% (4/10)',
            'test title: 50% (5/10)',
            'test title: 60% (6/10)',
            'test title: 70% (7/10)',
            'test title: 80% (8/10)',
            'test title: 90% (9/10)',
            'test title: 100% (10/10)',
        ])
        self.assertListEqual(list(lst), list(range(10)))

    def test_length(self):
        lst = MockInterface.from_iter(range(10), test_case=self, expected_outputs=[
            '0% (0/10)',
            '10% (1/10)',
            '20% (2/10)',
            '30% (3/10)',
            '40% (4/10)',
            '50% (5/10)',
            '60% (6/10)',
            '70% (7/10)',
            '80% (8/10)',
            '90% (9/10)',
            '100% (10/10)',
        ])
        self.assertListEqual(list(lst), list(range(10)))

    def test_iter_with_title(self):
        lst = MockInterface.from_iter(iter(range(10)), title='test iter', test_case=self, expected_outputs=[
            'test iter: 0/?',
            'test iter: 1/?',
            'test iter: 2/?',
            'test iter: 3/?',
            'test iter: 4/?',
            'test iter: 5/?',
            'test iter: 6/?',
            'test iter: 7/?',
            'test iter: 8/?',
            'test iter: 9/?',
            'test iter: 10/?',
        ])
        self.assertListEqual(list(lst), list(range(10)))
