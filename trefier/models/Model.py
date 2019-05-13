from enum import Enum
import sys
from zipfile import ZipFile
import pickle

__all__ = ['ModelPredictionType', 'Model']

class ModelPredictionType(Enum):
    # If the model predicts a single number representing the label
    LABELS = 'labels'
    
    # If the model predicts a probability value for all classes in a vector
    PROBABILITIES = 'probabilities'


class Model:
    def __init__(self, prediction_type, class_names):
        """ Model base
        Arguments:
            prediction_type: ModelPredictionType
            class_names: A dict of {int: str} that translates an integer label id to its text representation
        """
        assert isinstance(class_names, dict)
        assert all(isinstance(x, int) for x in class_names)
        assert all(isinstance(y, str) for y in class_names.values())

        self.settings = {
            'model_class': type(self).__name__,
            'prediction_type': ModelPredictionType(prediction_type),
            'class_names': class_names
        }
    
    def train(self):
        pass
    
    def predict_from_stdin(self, num_lines):
        # TODO: let the cli handle this function instead
        document = '\n'.join(
            line
            for line_num, line
            in zip(range(num_lines), sys.stdin)
        )
        return self.predict(document)
    
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
