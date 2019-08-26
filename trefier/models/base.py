from __future__ import annotations
from typing import List
import pickle
from zipfile import ZipFile

from trefier.models.tags import Tag

__all__ = ['Model']


class Model:
    MAJOR_VERSION = 2
    MINOR_VERSION = 1

    def __init__(self, predicts_probabilities, class_names):
        """ Model base
        Arguments:
            predicts_probabilities: True if model predicts probabilities, False if class labels.
            class_names: A dict of {int: str} that translates an integer label id to its text representation
        """
        assert isinstance(class_names, dict)
        assert all(isinstance(x, int) for x in class_names)
        assert all(isinstance(y, str) for y in class_names.values())

        self.version = {
            'major': Model.MAJOR_VERSION,
            'minor': Model.MINOR_VERSION,
        }

        self.settings = {
            'model_class': type(self).__name__,
            'predicts_probabilities': predicts_probabilities,
            'class_names': class_names
        }

    def train(self):
        raise NotImplementedError()

    def predict(self, file: str) -> List[Tag]:
        raise NotImplementedError()
    
    @classmethod
    def verify_loadable(self, path):
        try:
            with ZipFile(path) as package:
                settings = pickle.loads(package.read('settings.bin'))
            return settings['model_class'] == self.__name__
        except:
            return False
