from __future__ import annotations
from typing import Union, Optional, List

from keras import models
from keras.layers import *
from keras.preprocessing.sequence import pad_sequences
from keras.callbacks import EarlyStopping

import argh
import sys
from sklearn.model_selection import train_test_split
from collections import Counter
from zipfile import ZipFile
from tempfile import NamedTemporaryFile
import pickle
import re

from trefier import datasets, keywords, downloads
from trefier.misc import Evaluation
from trefier.misc.Cache import Cache
from trefier.models.base import Model
from trefier.models.tags import Tag
from trefier.tokenization.index_tokenizer import IndexTokenizer
from trefier.tokenization.streams import LatexTokenStream
from trefier.tokenization.latex import LatexParser

__all__ = ['Seq2SeqModel']


class Seq2SeqModel(Model):
    def __init__(self):
        super().__init__(
            predicts_probabilities=True,
            class_names={0: 'text', 1: 'keyword'})
        self.oov_tokenizer = None
        self.glove_tokenizer = None
        self.tfidf_model = None
        self.keyphraseness_model = None
        self.model = None

    @argh.arg('--epochs', type=int, help="Number of epochs to train the model for.")
    @argh.arg('--glove_ncomponents', type=int, help="Number of dimensions to reduce original glove embedding to.")
    @argh.arg('--glove_word_count', type=int, help="Limit available glove tokens (max 400k).")
    @argh.arg('--oov_embedding_dim', type=int, help="Dimensionality of the embedding used for tokens not in glove.")
    @argh.arg('--early_stopping_patience', type=int, help="Sets after how many epochs of no change, early stopping should stop training.")
    @argh.arg('--capacity', type=int, help="A linear factor for the model's capacity (min 1): Low capacity is less accurate, but high capacity requires a lot of data.")
    @argh.arg('--download_dir', type=str, help="Directory to which required training data will be downloaded.")
    @argh.arg('--oov_token', type=str, help="Special token used for all tokens not in glove.")
    @argh.arg('--math_token', type=str, help="Special token to use for math environments.")
    @argh.arg('--enable_pos_tags', help="Enables pos tag feature.")
    @argh.arg('--n_jobs', type=int, help="Number of processes parsing of files may use.")
    def train(
        self,
        epochs: int = 1,
        glove_ncomponents: int = 10,
        glove_word_count: Optional[int] = 200000,
        oov_embedding_dim: int = 4,
        early_stopping_patience: int = 5,
        capacity: int = 3,
        download_dir: str = 'data/',
        oov_token: str = '<oov>',
        math_token: str = '<math>',
        enable_pos_tags: bool = False,
        n_jobs: int = 6,):

        assert capacity > 0, "Capacity must be at least 1"
    
        assert 'seq2seq' not in self.settings
        self.settings['seq2seq'] = {
            'epochs': epochs,
            'glove_ncomponents': glove_ncomponents,
            'glove_word_count': glove_word_count,
            'oov_embedding_dim': oov_embedding_dim,
            'early_stopping_patience': early_stopping_patience,
            'capacity': capacity,
            'oov_token': oov_token,
            'math_token': math_token,
            'enable_pos_tags': enable_pos_tags,
        }

        with Cache(
            '/tmp/train-smglom-parser-cache.bin',
            lambda: list(datasets.smglom.parse_files(lang='en', download_dir=download_dir, n_jobs=n_jobs, show_progress=True))
        ) as cache:
            token_streams = cache.data
        assert token_streams is not None
        
        x, y = datasets.smglom.parse_dataset(token_streams, binary_labels=True, math_token=math_token, lang='en')
        
        glove_word_index, embedding_matrix, embedding_layer = downloads.glove.load(
            embedding_dim=50,
            oov_token=oov_token,
            num_words=min(glove_word_count, 400000) if glove_word_count else None,
            make_keras_layer=True,
            perform_pca=0 < glove_ncomponents < 50,
            n_components=glove_ncomponents
        )

        self.glove_tokenizer = IndexTokenizer(
            oov_token=oov_token
        ).fit_on_word_index(
            glove_word_index
        )

        self.oov_tokenizer = IndexTokenizer(
            oov_token=oov_token
        ).fit_on_word_index({
            word: i+1
            for i, word in enumerate(
                filter(
                    lambda word: word not in glove_word_index,
                    IndexTokenizer(oov_token=None).fit_on_sequences(x).word_index
                )
            )
        })

        print("oov tokenizer:", len(self.oov_tokenizer.word_index), 'are <oov>')

        self.tfidf_model = keywords.tfidf.TfIdfModel()
        self.keyphraseness_model = keywords.keyphraseness.KeyphrasenessModel()

        if enable_pos_tags:
            self.pos_tag_model = keywords.pos.PosTagModel()
        
        trainable_embedding_layer = Embedding(
            input_dim=len(self.oov_tokenizer.word_index) + 1,
            output_dim=oov_embedding_dim,
        )

        tokens_glove_input = Input((None,), name='tokens_glove', dtype=np.int32)
        tokens_oov_input = Input((None,), name='tokens_oov', dtype=np.int32)
        tfidf_input = Input((None,), name='tfidf', dtype=np.float32)
        keyphraseness_input = Input((None,), name='keyphraseness', dtype=np.float32)

        if enable_pos_tags:
            pos_tag_input = Input((None, self.pos_tag_model.num_categories), name='pos_tags', dtype=np.float32)
            print("Enabling pos_tag input")

        net = Concatenate()([
            embedding_layer(tokens_glove_input),
            trainable_embedding_layer(tokens_oov_input),
            Reshape((-1, 1))(tfidf_input),
            Reshape((-1, 1))(keyphraseness_input),
        ] + ([pos_tag_input] if enable_pos_tags else []))

        net = GaussianNoise(0.1)(net)
        net = Bidirectional(GRU(16*capacity, activation='tanh', dropout=0.1, return_sequences=True))(net)
        net = Bidirectional(GRU(16*capacity, activation='tanh', dropout=0.1, return_sequences=True))(net)
        net = Bidirectional(GRU(16*capacity, activation='tanh', dropout=0.1, return_sequences=True))(net)
        net = Dense(32*capacity, activation='sigmoid')(net)
        net = Dropout(0.5)(net)
        net = Dense(32*capacity, activation='sigmoid')(net)
        net = Dropout(0.5)(net)
        prediction_layer = Dense(1, activation='sigmoid')(net)

        self.model = models.Model(
            inputs=[
                tokens_glove_input,
                tokens_oov_input,
                tfidf_input,
                keyphraseness_input
            ] + ([pos_tag_input] if enable_pos_tags else []),
            outputs=prediction_layer
        )
        self.model.compile(
            optimizer='adam',
            loss='binary_crossentropy',
            metrics=['acc'],
            sample_weight_mode='temporal')
        self.model.summary()

        train_indices, test_indices = train_test_split(np.arange(len(y)))

        class_counts = np.array(list(dict(sorted(Counter(y_ for y_ in [y[ti] for ti in train_indices] for y_ in y_).items(), key=lambda x: x[0])).values()))
        class_weights = -np.log(class_counts / np.sum(class_counts))
        print("training set class counts", class_counts)
        print("training class weights", class_weights)

        sample_weights = [[class_weights[int(y_)] for y_ in y[i]] for i in train_indices]
        sample_weights = pad_sequences(sample_weights, maxlen=max(map(len, x)), dtype=np.float32)

        x_train = {}
        x_test = {}
        x_glove = pad_sequences(self.glove_tokenizer.transform(x))
        x_train['tokens_glove'] = x_glove[train_indices]
        x_test['tokens_glove'] = x_glove[test_indices]
        x_oov = pad_sequences(self.oov_tokenizer.transform(x))
        x_train['tokens_oov'] = x_oov[train_indices]
        x_test['tokens_oov'] = x_oov[test_indices]
        x_tfidf = pad_sequences(self.tfidf_model.fit_transform(x), dtype=np.float32)
        x_train['tfidf'] = x_tfidf[train_indices]
        x_test['tfidf'] = x_tfidf[test_indices]
        x_keyphraseness = pad_sequences(self.keyphraseness_model.fit_transform(x, y), dtype=np.float32)
        x_train['keyphraseness'] = x_keyphraseness[train_indices]
        x_test['keyphraseness'] = x_keyphraseness[test_indices]
        if enable_pos_tags:
            x_pos_tags = pad_sequences(self.pos_tag_model.predict(x), dtype=np.float32)
            x_train['pos_tags'] = x_pos_tags[train_indices]
            x_test['pos_tags'] = x_pos_tags[test_indices]
        
        y = np.expand_dims(pad_sequences(y), axis=-1)
        
        callbacks = [EarlyStopping(patience=early_stopping_patience)]

        fit_result = self.model.fit(
            sample_weight=sample_weights,
            epochs=epochs,
            callbacks=callbacks,
            x=x_train,
            y=y[train_indices],
            validation_data=(
                x_test,
                y[test_indices],
            ),
        )

        # evaluation stuff
        eval_y_pred_raw = self.model.predict(
            x_test
        ).squeeze(axis=-1)
        
        eval_y_true, eval_y_pred = zip(*[
            (true_, pred_)
            for x_, true_, pred_
            in zip(x_glove[test_indices], y[test_indices].squeeze(axis=-1), np.round(eval_y_pred_raw).astype(int))
            for x_, true_, pred_
            in zip(x_, true_, pred_)
            if x_ != 0 # remove padding
        ])

        self.evaluation = Evaluation.Evaluation(fit_result.history)
        self.evaluation.evaluate(np.array(eval_y_true), np.array(eval_y_pred), classes={0: 'text', 1: 'keyword'})
    
    @argh.arg('file', type=str, help="Path to file for which you want to make predictions for.")
    @argh.arg('--ignore_tagged_tokens', default=False, help="Disables already tagged token outputs")
    def predict(
        self,
        file: Union[str, LatexParser, LatexTokenStream],
        ignore_tagged_tokens: bool = True) -> List[Tag]:

        if file is None:
            raise Exception("Input file may not be None")
        
        if not isinstance(file, LatexTokenStream):
            parsed_file = LatexTokenStream.from_file(file)
        else:
            parsed_file = file
        
        if parsed_file is None:
            if isinstance(file, str):
                raise Exception(f'Failed to parse file "{file}"')
            else:
                raise Exception(f'Failed to create token stream from {file}')
        
        assert isinstance(parsed_file, LatexTokenStream)
        
        x = [[
            token.lexeme
            for token
            in parsed_file
        ]]

        X = {}

        if hasattr(self, 'glove_tokenizer') and self.glove_tokenizer is not None:
            x_glove = pad_sequences(self.glove_tokenizer.transform(x))
            X['tokens_glove'] = x_glove
        
        if hasattr(self, 'oov_tokenizer') and self.oov_tokenizer is not None:
            x_oov = pad_sequences(self.oov_tokenizer.transform(x))
            X['tokens_oov'] = x_oov

        if hasattr(self, 'tfidf_model') and self.tfidf_model is not None:
            x_tfidf = pad_sequences(self.tfidf_model.transform(x), dtype=np.float32)
            X['tfidf'] = x_tfidf

        if hasattr(self, 'keyphraseness_model') and self.keyphraseness_model is not None:
            x_keyphraseness = pad_sequences(self.keyphraseness_model.transform(x), dtype=np.float32)
            X['keyphraseness'] = x_keyphraseness
        
        if hasattr(self, 'pos_tag_model') and self.pos_tag_model is not None:
            x_pos_tags = pad_sequences(self.pos_tag_model.predict(x), dtype=np.float32)
            X['pos_tags'] = x_pos_tags

        y = self.model.predict(X).squeeze(0).squeeze(-1)

        is_tagged = re.compile(r'[ma]*(tr|d)efi+s?').fullmatch
        
        return [
            Tag(pred, token.token_range, token.lexeme)
            for token, pred
            in zip(parsed_file, y)
            if not ignore_tagged_tokens
            or not any(map(is_tagged, token.envs))
        ]
    
    def save(self, path):
        """ Saves the current state """
        with ZipFile(path, mode='w') as package:
            with NamedTemporaryFile() as ref:
                models.save_model(self.model, ref.name)
                ref.flush()
                package.write(ref.name, 'model.hdf5')
            h = hash(package.read('model.hdf5'))
            try:
                s = pickle.dumps(self.glove_tokenizer)
                h = hash(s ^ h)
                package.writestr('glove_tokenizer.bin', s)
            except:
                print('Warning: Failed to save "glove_tokenizer".', flush=True, file=sys.stderr)

            try:
                s = pickle.dumps(self.oov_tokenizer)
                h = hash(s ^ h)
                package.writestr('oov_tokenizer.bin', s)
            except:
                print('Warning: Failed to save "oov_tokenizer".', flush=True, file=sys.stderr)

            try:
                s = pickle.dumps(self.pos_tag_model)
                h = hash(s ^ h)
                package.writestr('pos_tag_model.bin', s)
            except:
                print('Warning: Failed to save "pos_tag_model".', flush=True, file=sys.stderr)

            try:
                s = pickle.dumps(self.tfidf_model)
                h = hash(s ^ h)
                package.writestr('tfidf_model.bin', s)
            except:
                print('Warning: Failed to save "tfidf_model".', flush=True, file=sys.stderr)

            try:
                s = pickle.dumps(self.keyphraseness_model)
                h = hash(s ^ h)
                package.writestr('keyphraseness_model.bin', s)
            except:
                print('Warning: Failed to save "keyphraseness_model".', flush=True, file=sys.stderr)
            
            s = pickle.dumps(self.evaluation)
            h = hash(s ^ h)
            package.writestr('evaluation.bin', s)
            
            s = pickle.dumps(self.settings)
            h = hash(s ^ h)
            package.writestr('settings.bin', s)
            
            s = pickle.dumps(self.version)
            h = hash(s ^ h)
            package.writestr('version.bin', s)
            
            try:
                package.writestr('hash', h)
            except:
                raise Exception("Failed to create model hash.")

    @staticmethod
    def load(path, append_extension=False):
        self = Seq2SeqModel()
        """ Loads the model from file """
        with ZipFile(path) as package:
            h = None
            with NamedTemporaryFile() as ref:
                s = package.read('model.hdf5')
                h = hash(s)
                ref.write(s)
                ref.flush()
                self.model = models.load_model(ref.name)

            try:
                s = package.read('glove_tokenizer.bin')
                h = hash(s ^ h)
                self.glove_tokenizer = pickle.loads(s)
            except:
                print('Warning: Failed to load "glove_tokenizer", setting it to None.', flush=True, file=sys.stderr)
                self.glove_tokenizer = None
            
            try:
                s = package.read('oov_tokenizer.bin')
                h = hash(s ^ h)
                self.oov_tokenizer = pickle.loads(s)
            except:
                print('Warning: Failed to load "oov_tokenizer", setting it to None.', flush=True, file=sys.stderr)
                self.oov_tokenizer = None

            try:
                s = package.read('pos_tag_model.bin')
                h = hash(s ^ h)
                self.pos_tag_model = pickle.loads(s)
            except:
                print('Warning: Failed to load "pos_tag_model", setting it to None.', flush=True, file=sys.stderr)
                self.pos_tag_model = None

            try:
                s = package.read('tfidf_model.bin')
                h = hash(s ^ h)
                self.tfidf_model = pickle.loads(s)
            except:
                print('Warning: Failed to load "tfidf_model", setting it to None.', flush=True, file=sys.stderr)
                self.tfidf_model = None

            try:
                s = package.read('keyphraseness_model.bin')
                h = hash(s ^ h)
                self.keyphraseness_model = pickle.loads(s)
            except:
                print('Warning: Failed to load "keyphraseness_model", setting it to None.', flush=True, file=sys.stderr)
                self.keyphraseness_model = None

            s = package.read('evaluation.bin')
            h = hash(s ^ h)
            self.evaluation = pickle.loads(s)
            
            s = package.read('settings.bin')
            h = hash(s ^ h)
            self.settings = pickle.loads(s)
            
            s = package.read('version.bin')
            h = hash(s ^ h)
            self.version = pickle.loads(s)

            if h != package.read('hash'):
                raise Exception(
                    'Hash of the tagger model could not be verified: '
                    f'Stored hash is {package.read("hash")}, '
                    f'loaded hash is {h}.')
            
            if self.version['major'] != Model.MAJOR_VERSION or self.version['minor'] < Model.MINOR_VERSION:
                raise Exception(
                    'Loaded model minor version mismatch: '
                    f'Loaded {self.version["major"]}.{self.version["minor"]}, '
                    f'but current version is {Model.MAJOR_VERSION}.{Model.MINOR_VERSION}.')

        return self

if __name__ == '__main__':
    global model
    model = Seq2SeqModel()
    
    @argh.arg("path", type=str, help="Path to a saved model file.")
    def load(path: str):
        """ Load a specific Seq2SeqModel from file. """
        global model
        model = Seq2SeqModel.load(path)
        if model is None:
            return "> Failed to load model from path %s" % path
        return "> Model loaded from %s" % path
    
    def show_evaluation():
        """ Plot evaluation of currently trained model. """
        try:
            model.evaluation.plot()
            return "> Showing evaluation"
        except:
            print("> Failed to plot model evaluation: Maybe the model didn't load or isn't trained yet.", file=sys.stderr, flush=True)

    class ExitException(Exception):
        pass
    
    def exit():
        """ Exits the cli. """
        raise ExitException()
    
    def reset():
        """ Resets the currently loaded model. """
        global model
        model = Seq2SeqModel()
        return "> Model reset"
    
    def show_keras_model_summary():
        """ Prints the model summary to stdout. """
        try:
            model.model.summary()
        except Exception as e:
            print("Error: %s" % str(e), file=sys.stderr, flush=True)

    def main():
        import shlex
        while True:
            try:
                for line in sys.stdin:
                        argh.dispatch_commands([
                            load,
                            model.train,
                            model.save,
                            model.predict,
                            show_evaluation,
                            show_keras_model_summary,
                            reset,
                            exit], shlex.split(line))
            except KeyboardInterrupt:
                print("> Exiting by user input")
                break
            except ExitException:
                return
            except Exception as e:
                print("Error: %s" % str(e), file=sys.stderr, flush=True)
    
    main()
