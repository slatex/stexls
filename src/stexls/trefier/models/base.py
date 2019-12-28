from __future__ import annotations
from typing import List
from enum import Enum
import json
from zipfile import ZipFile

from .tags import Tag


__all__ = ['Model']

class PredictionType(Enum):
    ''' Possible prediction types for a model are
    PROBABILITIES: Given a constant number of possible labels,
        this model predicts the probability distribution of labels.
    DISCRETE: Given a constant number of possible labels,
        this model predicts a number between 0 and #labels-1,
        representing the label the input belongs to.
    '''
    PROBABILITIES=1
    DISCRETE=2


class Model:
    def __init__(
        self,
        prediction_type: PredictionType,
        class_names: List[str],
        version: str):
        """ Initializes a model base by initializing the settings member with
            information about this model.
        Parameters:
            prediction_type: Prediction type.
            class_names: List of string identifiers for the corresponding labels.
            version: A string with the version of when this model was created.
        """
        assert isinstance(class_names, list)
        assert all(isinstance(x, str) for x in class_names)

        self.settings = {
            '__class__': type(self).__name__,
            'prediction_type': prediction_type.name,
            'class_names': class_names,
            'version': version
        }
    
    def supported_prediction_types(self) -> List[str]:
        ' Returns a list of prediction types this model supports. '
        return [self.settings['prediction_type']]
    
    def set_prediction_type(self, prediction_type: str) -> bool:
        ' Sets the prediction type for this model. '
        assert prediction_type in self.supported_prediction_types()
        self.settings['prediction_type'] = PredictionType[prediction_type].name

    def train(self):
        ' Executes the training operation of this model. '
        raise NotImplementedError()

    def predict(self, *files: str) -> List[List[Tag]]:
        ''' Generates predictions from files or text.
        Parameters:
            files: List of files to generate tags for.
        Returns:
            List of tags for every token for each file.
        '''
        raise NotImplementedError()
    
    @classmethod
    def verify_loadable(self, path: str) -> bool:
        ''' Verifies that the given path is loadable as the class of the caller.
            Models stored by this class must be packaged as a zip file and
            must contain the self.settings member serialized as json
            with the name "settings.json". In order to test for
            loadability, this settings.json is loaded and the "model_class"
            attribute is read and compared with the callers class.
        Parameters:
            path: Path to a file with the model.
        Returns:
            True if the path is a valid model of the callers class.
        '''
        try:
            with ZipFile(path) as package:
                settings = json.loads(package.read('settings.json').decode('utf-8'))
            return settings['model_class'] == self.__name__
        except:
            return False
