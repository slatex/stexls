import numpy as np

from keras import models
from keras.layers import *
from keras import backend as K
from keras.preprocessing.sequence import pad_sequences
from keras.callbacks import EarlyStopping

from sklearn.model_selection import train_test_split
from sklearn.utils.class_weight import compute_sample_weight, compute_class_weight

from itertools import chain
from collections import Counter
from zipfile import ZipFile
from tempfile import NamedTemporaryFile
import pickle

from . import ModelPredictionType, Model
from .. import datasets, keywords, tokenization, downloads
from ..misc import Evaluation

__all__ = ['Seq2SeqModel']

from ..misc import Cache

class Seq2SeqModel(Model):
    def __init__(self):
        super().__init__(
            prediction_type=ModelPredictionType.PROBABILITIES,
            class_names={0:'text', 1:'keyword'})
    
    def train(self, epochs=50, save_dir='data/', n_jobs=6):
        oov_token = '<oov>'
        math_token = '<math>'
        with Cache('/tmp/documents.bin', lambda: datasets.smglom.parse_files(save_dir='data/', n_jobs=n_jobs)) as cache:
            documents = cache.data
            print("Cache documents")
        X, Y = datasets.smglom.parse_dataset(documents, binary_labels=True)
        glove_word_index, embedding_matrix, embedding_layer = downloads.glove.load(50, oov_token=oov_token, make_keras_layer=True, perform_pca=True, n_components=10)

        # create a tokenizer for all words not in glove
        self.oov_tokenizer = tokenization.TexTokenizer(oov_token=oov_token, math_token=math_token)
        self.oov_tokenizer.fit_on_tex_files(documents, n_jobs=n_jobs)
        self.oov_tokenizer.word_index = {
            word: i+1
            for i, word in enumerate(filter(
                lambda word: word not in glove_word_index,
                self.oov_tokenizer.word_index
            ))
        }
        for special_token in ('<start>', '<stop>', '<oov>'):
            if special_token not in self.oov_tokenizer.word_index:
                self.oov_tokenizer.word_index[special_token] = len(self.oov_tokenizer.word_index) + 1

        print("oov tokenizer:", len(self.oov_tokenizer.word_index), 'are <oov>')

        # create a tokenizer for word with fixed glove embedding
        self.glove_tokenizer = tokenization.TexTokenizer(oov_token=oov_token, math_token=math_token)
        self.glove_tokenizer.word_index = glove_word_index

        self.tfidf_model = keywords.TfIdfModel(X)
        self.keyphraseness_model = keywords.KeyphrasenessModel(X, Y)
        
        trainable_embedding_layer = Embedding(
            input_dim=len(self.oov_tokenizer.word_index) + 1,
            output_dim=5,
        )

        tokens_glove_input = Input((None,), name='tokens_glove', dtype=np.int32)
        tokens_oov_input = Input((None,), name='tokens_oov', dtype=np.int32)
        tfidf_input = Input((None,), name='tfidf', dtype=np.float32)
        keyphraseness_input = Input((None,), name='keyphraseness', dtype=np.float32)

        net = Concatenate()([
            embedding_layer(tokens_glove_input),
            trainable_embedding_layer(tokens_oov_input),
            Reshape((-1, 1))(tfidf_input),
            Reshape((-1, 1))(keyphraseness_input),
        ])
        net = GaussianNoise(0.1)(net)
        net = Bidirectional(GRU(32, activation='tanh', dropout=0.1, return_sequences=True))(net)
        net = Bidirectional(GRU(32, activation='tanh', dropout=0.1, return_sequences=True))(net)
        net = Bidirectional(GRU(32, activation='tanh', dropout=0.1, return_sequences=True))(net)
        net = Dense(128, activation='sigmoid')(net)
        net = Dropout(0.5)(net)
        net = Dense(128, activation='sigmoid')(net)
        net = Dropout(0.5)(net)
        prediction_layer = Dense(1, activation='sigmoid')(net)

        self.model = models.Model(
            inputs=[
                tokens_glove_input,
                tokens_oov_input,
                tfidf_input,
                keyphraseness_input
            ],
            outputs=prediction_layer
        )
        self.model.compile(
            optimizer='adam',
            loss='binary_crossentropy',
            metrics=['acc'],
            sample_weight_mode='temporal')
        self.model.summary()

        train_indices, test_indices = train_test_split(np.arange(len(Y)))

        class_counts = np.array(list(dict(sorted(Counter(y_ for y_ in Y for y_ in y_).items(), key=lambda x: x[0])).values()))
        class_weights = -np.log(class_counts / np.sum(class_counts))
        sample_weights = [[class_weights[int(y_)] for y_ in Y[i]] for i in train_indices]
        sample_weights = pad_sequences(sample_weights, maxlen=max(map(len, X)), dtype=np.float32)

        X_glove = pad_sequences(self.glove_tokenizer.tokens_to_sequences(X))
        X_oov = pad_sequences(self.oov_tokenizer.tokens_to_sequences(X))

        X_tfidf = pad_sequences(self.tfidf_model.fit_transform(X), dtype=np.float32)
        X_keyphraseness = pad_sequences(self.keyphraseness_model.fit_transform(X, Y), dtype=np.float32)

        Y = np.expand_dims(pad_sequences(Y), axis=-1)
        
        callbacks = [EarlyStopping(patience=3)]

        fit_result = self.model.fit(
            sample_weight=sample_weights,
            epochs=epochs,
            callbacks=callbacks,
            x={
                'tokens_glove': X_glove[train_indices],
                'tokens_oov': X_oov[train_indices],
                'tfidf': X_tfidf[train_indices],
                'keyphraseness': X_keyphraseness[train_indices]
            },
            y=Y[train_indices],
            validation_data=(
                {
                    'tokens_glove': X_glove[test_indices],
                    'tokens_oov': X_oov[test_indices],
                    'tfidf': X_tfidf[test_indices],
                    'keyphraseness': X_keyphraseness[test_indices]
                },
                Y[test_indices],
            ),
        )

        # evaluation stuff
        eval_y_pred_raw = self.model.predict({
            'tokens_glove': X_glove[test_indices],
            'tokens_oov': X_oov[test_indices],
            'tfidf': X_tfidf[test_indices],
            'keyphraseness': X_keyphraseness[test_indices]
        }).squeeze(axis=-1)
        
        eval_y_true, eval_y_pred = zip(*[
            (true_, pred_)
            for x_, true_, pred_
            in zip(X_glove[test_indices], Y[test_indices].squeeze(axis=-1), np.round(eval_y_pred_raw).astype(int))
            for x_, true_, pred_
            in zip(x_, true_, pred_)
            if x_ != 0 # remove padding
        ])

        self.evaluation = Evaluation(fit_result.history)
        self.evaluation.evaluate(np.array(eval_y_true), np.array(eval_y_pred), classes={0:'text', 1:'keyword'})
    
    def predict(self, path_or_tex_document):
        document = tokenization.TexDocument(path_or_tex_document)
        if not document.success:
            return np.array([]), np.array([]), np.array([])
        tokens, offsets, envs = self.glove_tokenizer.tex_files_to_tokens([document], return_offsets_and_envs=True)
        X_glove = np.array(self.glove_tokenizer.tokens_to_sequences(tokens), dtype=np.int32)
        X_oov = np.array(self.oov_tokenizer.tokens_to_sequences(tokens), dtype=np.int32)
        X_tfidf = np.array(self.tfidf_model.transform(tokens), dtype=np.float32)
        X_keyphraseness = np.array(self.keyphraseness_model.transform(tokens), dtype=np.float32)
        y_pred = self.model.predict({
            'tokens_glove': X_glove,
            'tokens_oov': X_oov,
            'tfidf': X_tfidf,
            'keyphraseness': X_keyphraseness
        }).squeeze(axis=-1)

        positions = [tuple(map(document.offset_to_position, offset)) for offset in offsets[0]]

        return y_pred[0], positions, envs[0]
    
    def save(self, path):
        """ Saves the current state """
        with ZipFile(path, mode='w') as package:
            with NamedTemporaryFile() as ref:
                models.save_model(self.model, ref.name)
                ref.flush()
                package.write(ref.name, 'model.hdf5')
            package.writestr('glove_tokenizer.bin', pickle.dumps(self.glove_tokenizer))
            package.writestr('oov_tokenizer.bin', pickle.dumps(self.oov_tokenizer))
            #package.writestr('pos_embedder.bin', pickle.dumps(self.pos_embedder))
            package.writestr('tfidf_model.bin', pickle.dumps(self.tfidf_model))
            package.writestr('keyphraseness_model.bin', pickle.dumps(self.keyphraseness_model))
            package.writestr('evaluation.bin', pickle.dumps(self.evaluation))
            package.writestr('settings.bin', pickle.dumps(self.settings))

    
    @staticmethod
    def load(path, append_extension=False):
        self = Seq2SeqModel()
        """ Loads the model from file """
        with ZipFile(path) as package:
            with NamedTemporaryFile() as ref:
                ref.write(package.read('model.hdf5'))
                ref.flush()
                self.model = models.load_model(ref.name)
            self.glove_tokenizer = pickle.loads(package.read('glove_tokenizer.bin'))
            self.oov_tokenizer = pickle.loads(package.read('oov_tokenizer.bin'))
            #self.pos_embedder = pickle.loads(package.read('pos_embedder.bin'))
            self.tfidf_model = pickle.loads(package.read('tfidf_model.bin'))
            self.keyphraseness_model = pickle.loads(package.read('keyphraseness_model.bin'))
            self.evaluation = pickle.loads(package.read('evaluation.bin'))
            self.settings = pickle.loads(package.read('settings.bin'))
        return self
