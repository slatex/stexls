import pickle
from zipfile import ZipFile

__all__ = ['Model']


class Model:
    def __init__(self, predicts_probabilities, class_names):
        """ Model base
        Arguments:
            predicts_probabilities: True if model predicts probabilities, False if class labels.
            class_names: A dict of {int: str} that translates an integer label id to its text representation
        """
        assert isinstance(class_names, dict)
        assert all(isinstance(x, int) for x in class_names)
        assert all(isinstance(y, str) for y in class_names.values())

        self.settings = {
            'model_class': type(self).__name__,
            'predicts_probabilities': predicts_probabilities,
            'class_names': class_names
        }

    def train(self):
        pass

    def predict(self, path_or_tex_document):
        pass

    @classmethod
    def verify_loadable(self, path):
        try:
            with ZipFile(path) as package:
                settings = pickle.loads(package.read('settings.bin'))
            return settings['model_class'] == self.__name__
        except:
            return False