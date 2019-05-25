from sys import stdin, stderr
import argparse
import sys
import tempfile
from os.path import isfile, exists, isdir, expanduser, abspath
import argh
import re
import json

from loguru import logger

from .cli import CLI
from ..models import Seq2SeqModel
from ..tokenization import TexDocument

__all__ = ['ModelCLI']

class ModelCLI(CLI):
    def __init__(self):
        super().__init__()
        self.model = None
        self.logger = logger.bind(name="model_cli")
        self.logger.add(expanduser('~/.trefier/model_cli.log'), enqueue=True)
    
    @argh.arg('path', help="Path to model to load.")
    @argh.aliases('load')
    def load_model(self, path:str):
        """ Loads a new model as backend. """
        self.logger.info("Loading from %s" % abspath(path))

        self.logger.info("Check is file")
        if not isfile(path):
            self.logger.error("Specified path %s is not a file" % abspath(path))
            self.return_result(self.load_model, 1, message="%s is not a file." % abspath(path))
            return
        
        self.logger.info("Verify loadable Seq2Seq model")
        if not Seq2SeqModel.verify_loadable(path):
            self.logger.error("Specified path %s is not a valid Seq2SeqModel package" % abspath(path))
            self.return_result(self.load_model, 1, message="Failed to find model class of %s" % path)
            return

        try:
            self.logger.info("Attempting to load the file as a Seq2SeqModel")
            self.model = Seq2SeqModel.load(path)
        except Exception as e:
            self.logger.exception("Loading Seq2SeqModel failed")
            self.return_result(self.load_model, 1, message=str(e))
            return
        
        if self.model is None:
            self.logger.error("Seq2SeqModel.load returned None")
            self.return_result(self.load_model, 1, message="Could not create model from '%s'" % path)
            return

        self.logger.info("Returning success")
        self.return_result(self.load_model, 0, settings=self.model.settings)
    
    def _return_predictions(self, y_pred, positions, envs, ignore_tagged_tokens=False):
        self.logger.info(f"Parsing predictions (ignore_tagged_tokens={ignore_tagged_tokens})")
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
        self.logger.info(f"Returning {len(predictions)} predictions")
        self.return_result(self.predict, 0, predictions=predictions)
    
    @argh.arg('path_or_document', help="Path to the file or a tex document directly.")
    def predict(self, path_or_document):
        try:
            self.logger.info("predict from file or document")
            if self.model is None:
                self.logger.error("No model loaded")
                self.return_result(self.predict, 1, message="No backend model loaded")
            else:
                y_pred, positions, envs = self.model.predict(path_or_document)
                self.logger.info(f"model.predict created predictions for {len(y_pred)} tokens")
                self._return_predictions(y_pred, positions, envs)
        except Exception as e:
            self.logger.error(e)
            self.return_result(self.predict, 1, message=str(e))

    @argh.arg('num_lines', type=int, help="Number of lines sent over stdin.")
    def predict_from_stdin(self, num_lines):
        self.logger.info(f"Predicting from stdin expecting {num_lines} lines")
        document = ''.join(
            line
            for line_num, line
            in zip(range(num_lines), sys.stdin)
        )
        self.logger.info("Lines received: forwarding document to predict()")
        return self.predict(document)
    
    @argh.aliases('evaluation')
    def show_evaluation(self):
        self.logger.info("Running show_evaluation")
        try:
            if self.model is None:
                self.logger.error("No model loaded")
                self.return_result(self.show_evaluation, 1, message="No backend model loaded")
            else:
                self.logger.info("Displaying evaluation")
                self.model.evaluation.plot()
                self.return_result(self.show_evaluation, 0)
        except Exception as e:
            self.logger.exception("Exception thrown during show_evaluation")
            self.return_result(self.show_evaluation, 1, message=str(e))

    @argh.arg('save_dir', help="Path to where the trained model should be saved to.")
    @argh.arg('--model_class', help="Class of the model to train or None for the same class of the current model.")
    def train(self, save_dir:str, model_class:str=None):
        self.logger.info(f"training: save_dir={save_dir}, model_class={model_class or 'Default'}")
        try:
            model_class = {'Seq2SeqModel':Seq2SeqModel}.get(model_class, type(self.model))
            self.logger.info(f"Creating model for class {model_class}")
            self.model = model_class()
            self.logger.info("Starting training")
            self.model.train()
            self.logger.info("Saving model")
            self.model.save(save_dir)
            self.logger.info("Training finished")
        except:
            self.logger.exception("Exception during training")
            raise
    
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
        self.logger.info("run from %s" % abspath(path))
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
        self.logger.info("exiting model_cli")
