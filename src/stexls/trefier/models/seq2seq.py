from typing import Union, Optional, List, Callable
import json
import pickle
import os
import datetime
import numpy as np
from collections import Counter
from sklearn.model_selection import train_test_split
from zipfile import ZipFile
from tempfile import NamedTemporaryFile

import tensorflow as tf
from tensorflow import keras as k
from tensorflow.keras import models
from tensorflow.keras import layers
from tensorflow.keras import regularizers
from tensorflow.keras import callbacks
from tensorflow.keras.preprocessing.sequence import pad_sequences

from stexls.util.latex.tokenizer import LatexTokenizer
from stexls.trefier.training.datasets import smglom
from stexls.trefier.training.features.embedding import GloVe
from stexls.trefier.training.features.chisquare import ChiSquareModel
from stexls.trefier.training.features.tfidf import TfIdfModel
from stexls.trefier.training.features.keyphraseness import KeyphrasenessModel
from stexls.trefier.training.features.pos import PosTagModel
from . import base, tags

__all__ = ['Seq2SeqModel']

_VERSION_MAJOR = 1
_VERSION_MINOR = 0

class Seq2SeqModel(base.Model):
    def __init__(self):
        super().__init__(
            prediction_type=base.PredictionType.probabilities,
            class_names=['text', 'keyword'],
            version=f'{_VERSION_MAJOR}.{_VERSION_MINOR}'
        )
        self.model: tf.keras.models.Sequential = None
        self.tfidf_model: TfIdfModel = None
        self.keyphraseness_model: KeyphrasenessModel = None
        self.pos_tag_model: PosTagModel = None
        self.glove: GloVe = None

    def _create_data(
        self,
        download_dir: str,
        glove_n_components: int,
        val_split: float,
        test_split: float,
        cache_dir: str = None,
        progress: Optional[Callable] = None):
        print('Creating data...')
        x, y = smglom.load_and_cache(
            cache=os.path.join(cache_dir, 'smglom.bin'),
            download_dir=download_dir,
            progress=progress)
        print('Smglom loaded:', len(x), 'samples')
        x_train, x_valtest, y_train, y_valtest = train_test_split(
            x, y, test_size=val_split + test_split)
        x_val, x_test, y_val, y_test = train_test_split(
            x_valtest, y_valtest, test_size=test_split/(test_split + val_split))
        print(f'Train/val/test split: {len(x_train)}/{len(x_val)}/{len(x_test)}')
        self.glove = GloVe(
            n_components=glove_n_components,
            oov_vector='random',
            download_dir=cache_dir,
            extract_dir=download_dir)
        self.tfidf_model = TfIdfModel()
        self.keyphraseness_model = KeyphrasenessModel()
        self.pos_tag_model = PosTagModel()
        token_train = pad_sequences(self.glove.transform(x_train), dtype=np.float32)
        token_val = pad_sequences(self.glove.transform(x_val), dtype=np.float32)
        token_test = pad_sequences(self.glove.transform(x_test), dtype=np.float32)
        tfidf_train = np.expand_dims(pad_sequences(self.tfidf_model.fit_transform(x_train), dtype=np.float32), axis=-1)
        tfidf_val = np.expand_dims(pad_sequences(self.tfidf_model.transform(x_val), dtype=np.float32), axis=-1)
        tfidf_test = np.expand_dims(pad_sequences(self.tfidf_model.transform(x_test), dtype=np.float32), axis=-1)
        keyphraseness_train = np.expand_dims(pad_sequences(self.keyphraseness_model.fit_transform(x_train, y_train), dtype=np.float32), axis=-1)
        keyphraseness_val = np.expand_dims(pad_sequences(self.keyphraseness_model.transform(x_val), dtype=np.float32), axis=-1)
        keyphraseness_test = np.expand_dims(pad_sequences(self.keyphraseness_model.transform(x_test), dtype=np.float32), axis=-1)
        pos_train = pad_sequences(self.pos_tag_model.predict(x_train), dtype=np.float32)
        pos_val = pad_sequences(self.pos_tag_model.predict(x_val), dtype=np.float32)
        pos_test = pad_sequences(self.pos_tag_model.predict(x_test), dtype=np.float32)
        y_train = np.expand_dims(pad_sequences(y_train), axis=-1)
        y_val = np.expand_dims(pad_sequences(y_val), axis=-1)
        y_test = np.expand_dims(pad_sequences(y_test), axis=-1)

        x_train = {
            'tokens': token_train,
            'tfidf': tfidf_train,
            'keyphraseness': keyphraseness_train,
            'pos': pos_train,
        }

        x_val = {
            'tokens': token_val,
            'tfidf': tfidf_val,
            'keyphraseness': keyphraseness_val,
            'pos': pos_val,
        }

        x_test = {
            'tokens': token_test,
            'tfidf': tfidf_test,
            'keyphraseness': keyphraseness_test,
            'pos': pos_test,
        }
        
        return (x_train, y_train), (x_val, y_val), (x_test, y_test)

    def train(
        self,
        download_dir: str = '/tmp/seq2seq/downloads/',
        cache_dir: Optional[str] = '/tmp/seq2seq/cache/',
        log_dir: Optional[str] = '/tmp/seq2seq/logs/',
        save_dir: Optional[str] = '/tmp/seq2seq/models',
        epochs: int = 1,
        optimizer: str = 'adam',
        glove_n_components: int = 10,
        gaussian_noise: float = 0,
        capacity: int = 1,
        val_split: float = 0.1,
        test_split: float = 0.2,
        l2: float = 0.01,
        progress: Optional[Callable] = None):
    
        self.settings['seq2seq'] = {
            'epochs': epochs,
            'optimizer': optimizer,
            'n_components': glove_n_components,
            'gaussian_noise': gaussian_noise,
            'capacity': capacity,
            'val_split': val_split,
            'test_split': test_split,
            'l2': l2,
        }

        embedding_input = layers.Input((None, glove_n_components), name='tokens', dtype=tf.float32)
        tfidf_input = layers.Input((None, 1), name='tfidf', dtype=tf.float32)
        keyphraseness_input = layers.Input((None, 1), name='keyphraseness', dtype=tf.float32)
        pos_input = layers.Input((None, 35), name='pos', dtype=tf.float32)

        net_inputs = (embedding_input, tfidf_input, keyphraseness_input, pos_input)

        if 0 < gaussian_noise < 1:
            embedding_input = layers.GaussianNoise(gaussian_noise)(embedding_input)

        net = layers.Concatenate()([embedding_input, tfidf_input, keyphraseness_input, pos_input])
        net = layers.Bidirectional(layers.GRU(16*capacity, return_sequences=True))(net)
        net = layers.Bidirectional(layers.GRU(16*capacity, return_sequences=True))(net)
        net = layers.Bidirectional(layers.GRU(16*capacity, return_sequences=True))(net)
        net = layers.Dense(32*capacity, activation='relu', kernel_regularizer=regularizers.l2(l2))(net)
        net = layers.BatchNormalization()(net)
        net = layers.Dense(32*capacity, activation='relu', kernel_regularizer=regularizers.l2(l2))(net)
        net = layers.BatchNormalization()(net)
        prediction_layer = layers.Dense(1, activation='sigmoid')(net)

        self.model = models.Model(inputs=net_inputs, outputs=prediction_layer)

        self.model.compile(
            optimizer=optimizer,
            loss='binary_crossentropy',
            metrics=['acc'],
            sample_weight_mode='temporal')

        self.model.summary()

        (x_train, y_train), validation_data, (x_test, y_test) = self._create_data(
            download_dir=download_dir,
            glove_n_components=glove_n_components,
            val_split=val_split,
            test_split=test_split,
            cache_dir=cache_dir,
            progress=progress)
        
        class_count_counter = Counter(int(a) for b in y_train for a in b)
        print("Training set class counts", class_count_counter)

        num_classes = max(class_count_counter.keys()) + 1
        print('Num classes', num_classes)

        class_counts = np.zeros(num_classes, dtype=int)
        for cl, count in class_count_counter.items():
            class_counts[cl] = count

        self.class_weights = -np.log(class_counts / np.sum(class_counts))
        print("Training class weights", self.class_weights)

        sample_weights = np.array([
            [ self.class_weights[y2] for y2 in y1 ]
            for y1 in y_train.squeeze() ], dtype=float)
        print('Training sample weights:', sample_weights.shape)

        cb = []
        if log_dir:
            tb = callbacks.TensorBoard(log_dir, write_graph=True, histogram_freq=5)
            cb.append(tb)

        try:
            self.fit_result = self.model.fit(
                epochs=epochs,
                x=x_train,
                y=y_train,
                sample_weight=sample_weights,
                validation_data=validation_data,
                callbacks=cb)
        except KeyboardInterrupt:
            print('Model fit() interrupted by user input.')

        test_sample_weights = np.array([
            [ self.class_weights[y2] for y2 in y1 ]
            for y1 in y_test.squeeze() ], dtype=float)

        print('Evaluation of test samples')
        self.evaluation = self.model.evaluate(x_test, y_test, sample_weight=test_sample_weights)

        if save_dir:
            os.makedirs(save_dir, exist_ok=True)
            now = datetime.datetime.now()
            filename = now.strftime('%y-%m-%d.%H:%M:%S.model')
            filepath = os.path.join(save_dir, filename)
            print('Saving model to', filepath)
            self.save(filepath)
    
    def predict(self, *files: str) -> List[List[tags.Tag]]:
        documents = []
        all_tokens = []
        for tokenizer, file in zip(map(LatexTokenizer.from_file, files), files):
            if tokenizer is None:
                continue
            tokens = list(tokenizer)
            all_tokens.append(tokens)
            lexemes = [t.lexeme for t in tokens]
            documents.append(lexemes)
        inputs = {
            'tokens': pad_sequences(self.glove.transform(documents), dtype=np.float32),
            'keyphraseness': np.expand_dims(pad_sequences(self.keyphraseness_model.transform(documents), dtype=np.float32), axis=-1),
            'tfidf': np.expand_dims(pad_sequences(self.tfidf_model.transform(documents), dtype=np.float32), axis=-1),
            'pos': pad_sequences(self.pos_tag_model.predict(documents), dtype=np.float32),
        }
        return [
            [
                tags.Tag(float(pred[0]), token.begin, token.end)
                for pred, token in zip(doc[-len(tokens):], tokens)
            ]
            for doc, tokens in zip(self.model.predict(inputs), all_tokens)
        ]

    def save(self, path):
        """ Saves the current state """
        with ZipFile(path, mode='w') as package:
            print('Creating zip package:', path)
            tmpfile = NamedTemporaryFile(suffix='.h5')
            print('Temporarily saving keras model to', tmpfile.name)
            models.save_model(self.model, tmpfile.name)
            print('Adding', tmpfile.name, 'to package as model.h5')
            package.write(tmpfile.name, 'model.h5')
            print('Adding glove.bin', len(pickle.dumps(self.glove)), 'bytes.')
            package.writestr('glove.bin', pickle.dumps(self.glove))
            print('Adding tfidf_model.bin', len(pickle.dumps(self.tfidf_model)), 'bytes.')
            package.writestr('tfidf_model.bin', pickle.dumps(self.tfidf_model))
            print('Adding keyphraseness_model.bin', len(pickle.dumps(self.keyphraseness_model)), 'bytes.')
            package.writestr('keyphraseness_model.bin', pickle.dumps(self.keyphraseness_model))
            print('Adding pos_tag_model.bin', len(pickle.dumps(self.pos_tag_model)), 'bytes.')
            package.writestr('pos_tag_model.bin', pickle.dumps(self.pos_tag_model))
            print('Adding settings.json', len(json.dumps(self.settings, default=lambda x: x.__dict__)), 'characters.')
            package.writestr('settings.json', json.dumps(self.settings, default=lambda x: x.__dict__))

    @staticmethod
    def load(path) -> 'Seq2SeqModel':
        self = Seq2SeqModel()
        ' Loads the model from file '
        with ZipFile(path, 'r') as package:
            self.settings = json.loads(package.read('settings.json'))
            if self.settings['__class__'] != Seq2SeqModel.__name__:
                raise ValueError(f'Expected {Seq2SeqModel.__name__}, '
                                 f'but found {self.settings["__class__"]}')
            if int(self.settings['version'].split('.')[0]) != _VERSION_MAJOR:
                raise ValueError('Major version mismatch: '
                                f'{self.settings["version"]} vs. {_VERSION_MAJOR}.{_VERSION_MINOR}')
            self.glove = pickle.loads(package.read('glove.bin'))
            self.tfidf_model = pickle.loads(package.read('tfidf_model.bin'))
            self.keyphraseness_model = pickle.loads(package.read('keyphraseness_model.bin'))
            self.pos_tag_model = pickle.loads(package.read('pos_tag_model.bin'))
            with NamedTemporaryFile() as ref:
                ref.write(package.read('model.h5'))
                ref.flush()
                self.model = models.load_model(ref.name)
            assert self.model is not None
        return self

if __name__ == '__main__':
    from stexls.util.cli import Cli, command, Arg

    @command(
        epochs=Arg('--epochs', '-e', default=1, type=int, help='Number of epochs to train for.'),
        save_dir=Arg('--save_dir', '-s', default='/tmp/seq2seq/models', help='Directory where the finished model is saved to.'),
        download_dir=Arg('--download_dir', '-d', default='/tmp/seq2seq/downloads', help='Directory where downloads are saved to.'),
        log_dir=Arg('--log_dir', '-l', default='/tmp/seq2seq/logs', help='Directory for tensorboard logs.'),
        cache_dir=Arg('--cache_dir', '-c', default='/tmp/seq2seq/cache/', help='Path to directory for cache files.'))
    def train(epochs: int, save_dir: str, download_dir: str, log_dir: str, cache_dir: str):
        self = Seq2SeqModel()
        self.train(
            epochs=epochs,
            download_dir=download_dir,
            log_dir=log_dir,
            save_dir=save_dir,
            cache_dir=cache_dir,
        )
    
    @command(
        model=Arg('--model', '-m', required=True, help='Path to model to load.'),
        threshold=Arg('--threshold', '-t', type=float, default=0.5, help='.'),
        files=Arg(nargs='*', help='List of files to create predictions for.'))
    def predict(model: str, *files: str):
        self = Seq2SeqModel.load(model)
        print(self.predict(*files))
    
    cli = Cli([train, predict], 'Trains a seq2seq model or creates tags for a file.')
    cli.dispatch()
