from __future__ import annotations
from typing import Union, Optional, List

from keras import models
from keras.layers import *
from keras.preprocessing.sequence import pad_sequences
from keras.callbacks import EarlyStopping, TensorBoard, ReduceLROnPlateau

import json
import argh
import sys
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from collections import Counter
from zipfile import ZipFile
from tempfile import NamedTemporaryFile
import pickle
import re
import os

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
    MAJOR_VERSION = 1
    MINOR_VERSION = 0

    def __init__(self):
        super().__init__(
            predicts_probabilities=True,
            class_names={0: 'text', 1: 'keyword'},
            major_version=Seq2SeqModel.MAJOR_VERSION,
            minor_version=Seq2SeqModel.MINOR_VERSION,
        )
        self.model = None

    @argh.arg('-e', '--epochs', type=int, help="Number of epochs to train the model for.")
    @argh.arg('-o', '--optimizer', type=str, help="Name of the keras optimizer to use: adam, sgd, adagrad, rmsprop, etc...")
    @argh.arg('-n', '--glove_ncomponents', type=int, help="Number of dimensions to reduce original glove embedding to.")
    @argh.arg('-w', '--glove_word_count', type=int, help="Limit available glove tokens (max 400k).")
    @argh.arg('-E', '--enable_oov_embedding', help="Enables an extra trainable input embedding.")
    @argh.arg('-O', '--oov_embedding_dim', type=int, help="Dimensionality of the embedding used for tokens not in glove.")
    @argh.arg('-p', '--early_stopping_patience', type=int, help="Sets after how many epochs of no change, early stopping should stop training.")
    @argh.arg('-c', '--capacity', type=int, help="A linear factor for the model's capacity (min 1): Low capacity is less accurate, but high capacity requires a lot of data.")
    @argh.arg('-d', '--download_dir', type=str, help="Directory to which required training data will be downloaded.")
    @argh.arg('-t', '--oov_token', type=str, help="Special token used for all tokens not in glove.")
    @argh.arg('-m', '--math_token', type=str, help="Special token to use for math environments.")
    @argh.arg('-P', '--enable_pos_tags', help="Enables pos tag feature.")
    @argh.arg('-G', '--gaussian_noise', type=float, help="Gausian noise amplitude added to embedding vectors.")
    @argh.arg('-D', '--dense_dropout_percent', type=float, help="Dropout percentage for the two classifying dense layers.")
    @argh.arg('-R', '--recurrent_dropout_percent', type=float, help="Dropout percentage added to the recurrent layers.")
    @argh.arg('-b', '--tensorboard', help="Enables tensorboard logging to ~/.logs.")
    @argh.arg('-r', '--reduce_lr_on_plateau', help="Enables Keras ReduceLRonPlateau callback.")
    @argh.arg('-a', '--recurrent_activation', help="Activation function for recurrent layers.")
    @argh.arg('--log_gradients', help="Enables tensorboard gradient logging (requires -b option enabled).")
    @argh.arg('--normalize_input', help="Enables input normalization.")
    @argh.arg('-j', '--n_jobs', type=int, help="Number of processes parsing of files may use.")
    def train(
        self,
        epochs: int = 1,
        optimizer: str = 'adam',
        glove_ncomponents: int = 10,
        glove_word_count: Optional[int] = 200000,
        enable_oov_embedding: bool = False,
        oov_embedding_dim: int = 4,
        early_stopping_patience: int = 5,
        capacity: int = 3,
        download_dir: str = 'data/',
        oov_token: str = '<oov>',
        math_token: str = '<math>',
        enable_pos_tags: bool = False,
        gaussian_noise: float = 0.1,
        dense_dropout_percent: float = 0.5,
        recurrent_dropout_percent: float = 0.1,
        tensorboard: bool = False,
        reduce_lr_on_plateau: bool = False,
        recurrent_activation: str = 'tanh',
        log_gradients: bool = False,
        normalize_input: bool = False,
        n_jobs: int = 6,):

        assert capacity > 0, "Capacity must be at least 1"
    
        assert 'seq2seq' not in self.settings
        self.settings['seq2seq'] = {
            'epochs': epochs,
            'optimizer': optimizer,
            'enable_oov_embedding': enable_oov_embedding,
            'glove_ncomponents': glove_ncomponents,
            'glove_word_count': glove_word_count,
            'oov_embedding_dim': oov_embedding_dim,
            'early_stopping_patience': early_stopping_patience,
            'capacity': capacity,
            'oov_token': oov_token,
            'math_token': math_token,
            'gaussian_noise': gaussian_noise,
            'dense_dropout_percent': dense_dropout_percent,
            'recurrent_dropout_percent': recurrent_dropout_percent,
            'enable_pos_tags': enable_pos_tags,
            'reduce_lr_on_plateau': reduce_lr_on_plateau,
            'recurrent_activation': recurrent_activation,
            'normalize_input': normalize_input,
        }

        print("train seq2seq model settings:")
        print(self.settings['seq2seq'])

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

        if enable_oov_embedding:
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

        # list of all input layers
        net_inputs = []

        # list of all the transformed input layers that have to be concatenated
        net_concatenate_inputs = []
        
        if enable_oov_embedding:
            print("Enabling oov token embedding")
            tokens_oov_input = Input((None,), name='tokens_oov', dtype=np.int32)
            net_inputs.append(tokens_oov_input)
            trainable_embedding_layer = Embedding(
                input_dim=len(self.oov_tokenizer.word_index) + 1,
                output_dim=oov_embedding_dim,
                name='trainable_embedding'
            )
            embedded_oov_tokens = trainable_embedding_layer(tokens_oov_input)
            if 0 < gaussian_noise < 1:
                print("Enable oov gaussian noise", gaussian_noise)
                embedded_oov_tokens = GaussianNoise(gaussian_noise)(embedded_oov_tokens)
            net_concatenate_inputs.append(embedded_oov_tokens)

        tokens_glove_input = Input((None,), name='tokens_glove', dtype=np.int32)
        net_inputs.append(tokens_glove_input)
        embedded_glove_tokens = embedding_layer(tokens_glove_input)
        if 0 < gaussian_noise < 1:
            print("Enable glove gaussian noise", gaussian_noise)
            embedded_glove_tokens = GaussianNoise(gaussian_noise)(embedded_glove_tokens)
        net_concatenate_inputs.append(embedded_glove_tokens)
        
        tfidf_input = Input((None,), name='tfidf', dtype=np.float32)
        net_inputs.append(tfidf_input)
        tfidf_transform = Reshape((-1, 1))(tfidf_input)
        if normalize_input:
            tfidf_transform = BatchNormalization()(tfidf_transform)
            print("Enable tfidf batch normalization")
        net_concatenate_inputs.append(tfidf_transform)

        keyphraseness_input = Input((None,), name='keyphraseness', dtype=np.float32)
        net_inputs.append(keyphraseness_input)
        keyphraseness_transform = Reshape((-1, 1))(keyphraseness_input)
        if normalize_input:
            keyphraseness_transform = BatchNormalization()(keyphraseness_transform)
            print("Enable keyphraseness batch normalization")
        net_concatenate_inputs.append(keyphraseness_transform)

        if enable_pos_tags:
            print("Enabling pos_tag input")
            pos_tag_input = Input((None, self.pos_tag_model.num_categories), name='pos_tags', dtype=np.float32)
            net_inputs.append(pos_tag_input)
            net_concatenate_inputs.append(pos_tag_input)

        net = Concatenate()(net_concatenate_inputs)
        if not (0 < recurrent_dropout_percent < 1):
            recurrent_dropout_percent = 0
        net = Bidirectional(GRU(16*capacity, activation=recurrent_activation, dropout=recurrent_dropout_percent, return_sequences=True))(net)
        if recurrent_activation == 'relu':
            net = BatchNormalization()(net)
        net = Bidirectional(GRU(16*capacity, activation=recurrent_activation, dropout=recurrent_dropout_percent, return_sequences=True))(net)
        if recurrent_activation == 'relu':
            net = BatchNormalization()(net)
        net = Bidirectional(GRU(16*capacity, activation=recurrent_activation, dropout=recurrent_dropout_percent, return_sequences=True))(net)
        if recurrent_activation == 'relu':
            net = BatchNormalization()(net)
        net = Dense(32*capacity, activation='sigmoid')(net)
        if 0 < dense_dropout_percent < 1:
            net = Dropout(dense_dropout_percent)(net)
        net = Dense(32*capacity, activation='sigmoid')(net)
        if 0 < dense_dropout_percent < 1:
            net = Dropout(dense_dropout_percent)(net)
        prediction_layer = Dense(1, activation='sigmoid')(net)

        self.model = models.Model(
            inputs=net_inputs,
            outputs=prediction_layer
        )

        self.model.compile(
            optimizer=optimizer,
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
        
        original_y = y
        y = np.expand_dims(pad_sequences(y), axis=-1)

        x_train = {}
        x_test = {}

        x_glove = pad_sequences(self.glove_tokenizer.transform(x))
        x_train['tokens_glove'] = x_glove[train_indices]
        x_test['tokens_glove'] = x_glove[test_indices]

        if enable_oov_embedding:
            x_oov = pad_sequences(self.oov_tokenizer.transform(x))
            x_train['tokens_oov'] = x_oov[train_indices]
            x_test['tokens_oov'] = x_oov[test_indices]
        
        x_tfidf = self.tfidf_model.fit_transform(x)
        # if normalize_input:
        #     self.tfidf_normalizer = StandardScaler()
        #     x_tfidf = self.tfidf_normalizer.fit_transform(x_tfidf)
        #     print("Enable tfidf normalizer")
        x_tfidf = pad_sequences(x_tfidf, dtype=np.float32)
        x_train['tfidf'] = x_tfidf[train_indices]
        x_test['tfidf'] = x_tfidf[test_indices]
        
        x_keyphraseness = self.keyphraseness_model.fit_transform(x, original_y)
        # if normalize_input:
        #     self.keyphraseness_normalizer = StandardScaler()
        #     x_keyphraseness = self.keyphraseness_normalizer.fit_transform(x_keyphraseness)
        #     print("Enable keyphraseness normalizer")
        x_keyphraseness = pad_sequences(x_keyphraseness, dtype=np.float32)
        x_train['keyphraseness'] = x_keyphraseness[train_indices]
        x_test['keyphraseness'] = x_keyphraseness[test_indices]

        if enable_pos_tags:
            x_pos_tags = pad_sequences(self.pos_tag_model.predict(x), dtype=np.float32)
            x_train['pos_tags'] = x_pos_tags[train_indices]
            x_test['pos_tags'] = x_pos_tags[test_indices]
        
        callbacks = [
            EarlyStopping(patience=early_stopping_patience)
        ]

        if tensorboard:
            print(f'Tensorboard enabled: Logging to "{os.path.abspath("./logs")}"')
            if not enable_oov_embedding:
                print("Without oov embedding, tensorboard embedding visualization can't be enabled.")
            callbacks.append(
                TensorBoard(
                    log_dir='./logs',
                    histogram_freq=2 if log_gradients else 1,
                    batch_size=len(x_train),
                    write_graph=True,
                    write_grads=log_gradients,
                    write_images=False,
                    # embeddings_freq=3 if enable_oov_embedding else 0,
                    # embeddings_layer_names=['trainable_embedding'] if enable_oov_embedding else None,
                    # embeddings_metadata=None,
                    # embeddings_data=x_test,
                    update_freq='epoch'
                )
            )

        if reduce_lr_on_plateau:
            print("Reduce learning rate on plateau enabled")
            callbacks.append(
                ReduceLROnPlateau(
                    monitor='val_loss',
                    factor=0.2,
                    patience=5,
                    min_lr=0.001
                )
            )

        try:
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
        except KeyboardInterrupt:
            print("Model fitting interrupted by user input: No evaluation will be created.")
            self.evaluation = None
            return

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
            x_tfidf = self.tfidf_model.transform(x)
            if hasattr(self, 'tfidf_normalizer') and self.tfidf_normalizer is not None:
                x_tfidf = self.tfidf_normalizer.transform(x_tfidf)
            x_tfidf = pad_sequences(x_tfidf, dtype=np.float32)
            X['tfidf'] = x_tfidf

        if hasattr(self, 'keyphraseness_model') and self.keyphraseness_model is not None:
            x_keyphraseness = self.keyphraseness_model.transform(x)
            if hasattr(self, 'keyphraseness_normalizer') and self.keyphraseness_normalizer is not None:
                x_keyphraseness = self.keyphraseness_normalizer.transform(x_keyphraseness)
            x_keyphraseness = pad_sequences(x_keyphraseness, dtype=np.float32)
            X['keyphraseness'] = x_keyphraseness
        
        if hasattr(self, 'pos_tag_model') and self.pos_tag_model is not None:
            x_pos_tags = pad_sequences(self.pos_tag_model.predict(x), dtype=np.float32)
            X['pos_tags'] = x_pos_tags

        y = self.model.predict(X).squeeze(0).squeeze(-1)

        is_tagged = re.compile(r'[ma]*(tr|d)efi+s?').fullmatch if ignore_tagged_tokens else None
        
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
            
            try:
                package.writestr('glove_tokenizer.bin', pickle.dumps(self.glove_tokenizer))
            except Exception as e:
                print(str(e), flush=True, file=sys.stderr)
                print('Warning: Failed to save "glove_tokenizer".', flush=True, file=sys.stderr)

            try:
                package.writestr('oov_tokenizer.bin', pickle.dumps(self.oov_tokenizer))
            except Exception as e:
                print(str(e), flush=True, file=sys.stderr)
                print('Warning: Failed to save "oov_tokenizer".', flush=True, file=sys.stderr)

            try:
                package.writestr('pos_tag_model.bin', pickle.dumps(self.pos_tag_model))
            except Exception as e:
                print(str(e), flush=True, file=sys.stderr)
                print('Warning: Failed to save "pos_tag_model".', flush=True, file=sys.stderr)

            try:
                package.writestr('tfidf_model.bin', pickle.dumps(self.tfidf_model))
            except Exception as e:
                print(str(e), flush=True, file=sys.stderr)
                print('Warning: Failed to save "tfidf_model".', flush=True, file=sys.stderr)

            try:
                package.writestr('tfidf_normalizer.bin', pickle.dumps(self.tfidf_normalizer))
            except Exception as e:
                print(str(e), flush=True, file=sys.stderr)
                print('Warning: Failed to save "tfidf_normalizer".', flush=True, file=sys.stderr)

            try:
                package.writestr('keyphraseness_model.bin', pickle.dumps(self.keyphraseness_model))
            except Exception as e:
                print(str(e), flush=True, file=sys.stderr)
                print('Warning: Failed to save "keyphraseness_model".', flush=True, file=sys.stderr)

            try:
                package.writestr('keyphraseness_normalizer.bin', pickle.dumps(self.keyphraseness_normalizer))
            except Exception as e:
                print(str(e), flush=True, file=sys.stderr)
                print('Warning: Failed to save "keyphraseness_normalizer".', flush=True, file=sys.stderr)
            
            package.writestr('evaluation.bin', pickle.dumps(self.evaluation))
            
            package.writestr('settings.json', json.dumps(self.settings, default=lambda x: x.__dict__).encode('utf-8'))
            
            package.writestr('version', f'{self.version["major"]}.{self.version["minor"]}'.encode('utf-8'))

    @staticmethod
    def load(path):
        self = Seq2SeqModel()
        """ Loads the model from file """
        with ZipFile(path) as package:
            with NamedTemporaryFile() as ref:
                ref.write(package.read('model.hdf5'))
                ref.flush()
                self.model = models.load_model(ref.name)
            
            assert self.model is not None

            try:
                self.glove_tokenizer = pickle.loads(package.read('glove_tokenizer.bin'))
            except Exception as e:
                print(str(e), flush=True, file=sys.stderr)
                print('Warning: Failed to load "glove_tokenizer."', flush=True, file=sys.stderr)
            
            try:
                self.oov_tokenizer = pickle.loads(package.read('oov_tokenizer.bin'))
            except Exception as e:
                print(str(e), flush=True, file=sys.stderr)
                print('Warning: Failed to load "oov_tokenizer."', flush=True, file=sys.stderr)

            try:
                self.pos_tag_model = pickle.loads(package.read('pos_tag_model.bin'))
            except Exception as e:
                print(str(e), flush=True, file=sys.stderr)
                print('Warning: Failed to load "pos_tag_model."', flush=True, file=sys.stderr)

            try:
                self.tfidf_model = pickle.loads(package.read('tfidf_model.bin'))
            except Exception as e:
                print(str(e), flush=True, file=sys.stderr)
                print('Warning: Failed to load "tfidf_model."', flush=True, file=sys.stderr)

            try:
                self.tfidf_normalizer = pickle.loads(package.read('tfidf_normalizer.bin'))
            except Exception as e:
                print(str(e), flush=True, file=sys.stderr)
                print('Warning: Failed to load "tfidf_normalizer."', flush=True, file=sys.stderr)

            try:
                self.keyphraseness_model = pickle.loads(package.read('keyphraseness_model.bin'))
            except Exception as e:
                print(str(e), flush=True, file=sys.stderr)
                print('Warning: Failed to load "keyphraseness_model."', flush=True, file=sys.stderr)

            try:
                self.keyphraseness_normalizer = pickle.loads(package.read('keyphraseness_normalizer.bin'))
            except Exception as e:
                print(str(e), flush=True, file=sys.stderr)
                print('Warning: Failed to load "keyphraseness_normalizer."', flush=True, file=sys.stderr)

            self.evaluation = pickle.loads(package.read('evaluation.bin'))
            
            self.settings = json.loads(package.read('settings.json').decode('utf-8'))
            
            self.version = {}
            self.version['major'], self.version['minor'] = map(int, package.read('version').decode('utf-8').split('.'))
            
            if self.version['major'] != Seq2SeqModel.MAJOR_VERSION or self.version['minor'] < Seq2SeqModel.MINOR_VERSION:
                raise Exception(
                    'Loaded model minor version mismatch: '
                    f'Loaded {self.version["major"]}.{self.version["minor"]}, '
                    f'but current version is {Seq2SeqModel.MAJOR_VERSION}.{Seq2SeqModel.MINOR_VERSION}.')

        return self

if __name__ == '__main__':
 
    global model
 
    model = Seq2SeqModel()
 
    from trefier.app.cli import CLI, CLIRestartException, CLIExitException

    class Seq2SeqCli(CLI):
        def run(self, *extra_commands):
            super().run([
                self.load,
                self.show_evaluation,
                self.reset,
                self.show_keras_model_summary,
                super().exit,
                *extra_commands
            ])
        
        @argh.arg("path", type=str, help="Path to a saved model file.")
        def load(self, path: str):
            """ Load a specific Seq2SeqModel from file. """
            global model
            model = Seq2SeqModel.load(path)
            if model is None:
                return "> Failed to load model from path %s" % path
            return "> Model loaded from %s" % path
        
        def show_evaluation(self):
            """ Plot evaluation of currently trained model. """
            try:
                model.evaluation.plot()
                return "> Showing evaluation"
            except:
                print("> Failed to plot model evaluation: Maybe the model didn't load or isn't trained yet.", file=sys.stderr, flush=True)

        def reset(self):
            """ Resets the currently loaded model. """
            global model
            model = Seq2SeqModel()
            return "> Model reset"
        
        def show_keras_model_summary(self):
            """ Prints the model summary to stdout. """
            try:
                model.model.summary()
            except Exception as e:
                print("Error: %s" % str(e), file=sys.stderr, flush=True)

    @argh.arg('path', help="Path to file.")
    @argh.arg('--ignore_tagged_tokens', help="If enabeld, tokens that already have a tag are not written to the output.")
    def predict(
        path: str,
        ignore_tagged_tokens: bool = True):
        """ Reads the file from the given path and returns predicted tags """
        return model.predict(path, ignore_tagged_tokens)

    Seq2SeqCli().run(model.train, model.save, predict)
