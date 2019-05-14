from sys import stdin, stderr
import argparse
import sys
import tempfile
from os.path import isfile, exists, isdir
import argh
import re

from .cli import CLI
from ..models import Seq2SeqModel, ModelPredictionType

__all__ = ['ModelCLI']

class ModelCLI(CLI):
    def __init__(self):
        super().__init__()
        self.model = None
    
    @argh.arg('path', help="Path to model to load.")
    @argh.aliases('load')
    def load_model(self, path:str):
        """ Loads a new model as backend. """
        if not isfile(path):
            self.return_result(self.load_model, 1, message="%s is not a file." % path)
            return
        
        if not Seq2SeqModel.verify_loadable(path):
            self.return_result(self.load_model, 1, message="Failed to find model class of %s" % path)
            return

        self.model = Seq2SeqModel.load(path)

        if self.model is None:
            self.return_result(self.load_model, 1, message="Could not create model from '%s'" % path)
            return

        labels = '{' + ','.join(
            f'"{name}":{index}'
            for index, name
            in self.model.settings['class_names'].items()
        ) + '}'

        prediction_type = self.model.settings['prediction_type'].value

        self.return_result(
            self.load_model,
            0,
            prediction_type=f'"{prediction_type}"',
            class_names=labels)
    
    def _return_predictions(self, y_pred, positions, envs, ignore_tagged_tokens=False):
        predictions = ','.join(
            f'{{"range":{{"begin":{{"line":{bl},"column":{bc}}},"end":{{"line":{el},"column":{ec}}}}},"y_pred":{preds}}}'
            for preds, ((bl, bc), (el, ec)), envs
            in zip(y_pred, positions, envs)
            if not ignore_tagged_tokens or not any(map(re.compile(r'[ma]*(tr|d)efi+s?').fullmatch, envs))
        )
        self.return_result(self.predict_from_file, 0, predictions=f"[{predictions}]")
    
    @argh.arg('path', help="Path to the file.")
    @argh.aliases('predict')
    def predict_from_file(self, path):
        try:
            if not isfile(path):
                self.return_result(self.predict_from_file, 1, predictions="[]", message=f'"Failed to open file {path}"')
            else:
                y_pred, positions, envs = self.model.predict(path)
                self._return_predictions(y_pred, positions, envs)
        except Exception as e:
            self.return_result(self.predict_from_file, 0, predictions="[]", message=f'"{str(e)}"')
    
    @argh.aliases('evaluation')
    def show_evaluation(self):
        try:
            self.model.evaluation.plot()
            self.return_result(self.show_evaluation, 0)
        except Exception as e:
            self.return_result(self.show_evaluation, 1, message=f'"{str(e)}"')

    @argh.arg('save_dir', help="Path to where the trained model should be saved to.")
    @argh.arg('--model_class', help="Class of the model to train or None for the same class of the current model.")
    def train(self, save_dir:str, model_class:str=None):
        model_class = {'Seq2SeqModel':Seq2SeqModel}.get(model_class, type(self.model))
        self.model = model_class()
        self.model.train()
        self.model.save(save_dir)
    
    def run(self, path=None):
        """ Runs model cli.
        Arguments:
            :param path: Path to model
            :param model_class: Optional model class if the model from the given path does not have a standard extension.
        """
        if path:
            self.load_model(path)
        super().run([
            self.train,
            self.load_model,
            self.predict_from_file,
            self.show_evaluation,
        ])
