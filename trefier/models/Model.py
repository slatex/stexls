from enum import Enum
import sys

__all__ = ['ModelPredictionType', 'Model']

class ModelPredictionType(Enum):
    # If the model predicts a single number representing the label
    LABELS = 'labels'
    
    # If the model predicts a probability value for all classes in a vector
    PROBABILITIES = 'probabilities'


class Model:
    def __init__(self, prediction_type, label_names):
        """ Model base
        Arguments:
            prediction_type: ModelPredictionType
            label_names: A dict of {int: str} that translates an integer label id to its text representation
        """
        assert isinstance(label_names, dict)
        assert all(isinstance(x, int) for x in label_names)
        assert all(isinstance(y, str) for y in label_names.values())

        self.settings = {
            'model_class': type(self).__name__,
            'prediction_type': ModelPredictionType(prediction_type),
            'label_names': label_names
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
