from sys import stdin, stderr
import argparse
import sys
import tempfile
from os.path import isfile, exists, isdir
import argh
import re
import json

from .cli import CLI
from ..models import Seq2SeqModel
from ..tokenization import TexDocument

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

        self.return_result(self.load_model, 0, settings=self.model.settings)
    
    def _return_predictions(self, y_pred, positions, envs, ignore_tagged_tokens=False):
        predictions = [
            {
                "range": {
                    "begin":{"line":begin_line, "column": begin_column},
                    "end":{"line":end_line, "column": end_column},
                },
                "y_pred": preds.tolist()
            }
            for preds, ((begin_line, begin_column), (end_line, end_column)), envs
            in zip(y_pred, positions, envs)
            if not ignore_tagged_tokens or not any(map(re.compile(r'[ma]*(tr|d)efi+s?').fullmatch, envs))
        ]
        self.return_result(self.predict, 0, predictions=predictions)
    
    @argh.arg('path', help="Path to the file.")
    def predict(self, path):
        try:
            if self.model is None:
                self.return_result(self.predict, 1, message="No backend model loaded")
            else:
                y_pred, positions, envs = self.model.predict(path)
                self._return_predictions(y_pred, positions, envs)
        except Exception as e:
            self.return_result(self.predict, 1, message=str(e))

    @argh.arg('num_lines', type=int, help="Number of lines sent over stdin.")
    def predict_from_stdin(self, num_lines):
        document = ''.join(
            line
            for line_num, line
            in zip(range(num_lines), sys.stdin)
        )
        return self.predict(document)
    
    @argh.aliases('evaluation')
    def show_evaluation(self):
        try:
            if self.model is None:
                self.return_result(self.show_evaluation, 1, message="No backend model loaded")
            else:
                self.model.evaluation.plot()
                self.return_result(self.show_evaluation, 0)
        except Exception as e:
            self.return_result(self.show_evaluation, 1, message=str(e))

    @argh.arg('save_dir', help="Path to where the trained model should be saved to.")
    @argh.arg('--model_class', help="Class of the model to train or None for the same class of the current model.")
    def train(self, save_dir:str, model_class:str=None):
        model_class = {'Seq2SeqModel':Seq2SeqModel}.get(model_class, type(self.model))
        self.model = model_class()
        self.model.train()
        self.model.save(save_dir)
    
    @argh.arg('s', help="Number of seconds to sleep.", type=float)
    def wait(self, s):
        import time
        time.sleep(s)
        self.return_result(self.wait, 0, message="Waited %.02f seconds." % s)
    
    def run(self, path=None):
        """ Runs model cli.
        Arguments:
            :param path: Path to model
            :param model_class: Optional model class if the model from the given path does not have a standard extension.
        """
        if path:
            self.load_model(path)
        super().run([
            self.wait,
            self.train,
            self.load_model,
            self.predict,
            self.predict_from_stdin,
            self.show_evaluation,
        ])
