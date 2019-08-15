from __future__ import annotations
from typing import Union, Optional, List

from keras import models
from keras.layers import *
from keras.preprocessing.sequence import pad_sequences
from keras.callbacks import EarlyStopping

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

    def train(
        self,
        epochs: int = 1,
        glove_ncomponents: int = 10,
        glove_word_count: Optional[int] = 200000,
        oov_embedding_dim: int = 4,
        early_stopping_patience: int = 5,
        save_dir: str = 'data/',
        oov_token: str = '<oov>',
        math_token:str = '<math>',
        n_jobs: int = 6,):
        with Cache(
            '/tmp/train-smglom-parser-cache.bin',
            lambda: list(datasets.smglom.parse_files(lang='en', save_dir=save_dir, n_jobs=n_jobs, show_progress=True))
        ) as cache:
            token_streams = cache.data
        assert token_streams is not None
        
        x, y = datasets.smglom.parse_dataset(token_streams, binary_labels=True, math_token=math_token, lang='en')
        
        glove_word_index, embedding_matrix, embedding_layer = downloads.glove.load(
            embedding_dim=50,
            oov_token=oov_token,
            num_words=min(glove_word_count, 400000) if glove_word_count else None,
            make_keras_layer=True,
            perform_pca=glove_ncomponents < 50,
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
        self.pos_tag_model = keywords.pos.PosTagModel()
        
        trainable_embedding_layer = Embedding(
            input_dim=len(self.oov_tokenizer.word_index) + 1,
            output_dim=oov_embedding_dim,
        )

        tokens_glove_input = Input((None,), name='tokens_glove', dtype=np.int32)
        tokens_oov_input = Input((None,), name='tokens_oov', dtype=np.int32)
        tfidf_input = Input((None,), name='tfidf', dtype=np.float32)
        keyphraseness_input = Input((None,), name='keyphraseness', dtype=np.float32)
        pos_tag_input = Input((None, self.pos_tag_model.num_categories), name='pos_tags', dtype=np.float32)

        net = Concatenate()([
            embedding_layer(tokens_glove_input),
            trainable_embedding_layer(tokens_oov_input),
            Reshape((-1, 1))(tfidf_input),
            Reshape((-1, 1))(keyphraseness_input),
            pos_tag_input,
        ])
        net = GaussianNoise(0.1)(net)
        net = Bidirectional(GRU(48, activation='tanh', dropout=0.1, return_sequences=True))(net)
        net = Bidirectional(GRU(48, activation='tanh', dropout=0.1, return_sequences=True))(net)
        net = Bidirectional(GRU(48, activation='tanh', dropout=0.1, return_sequences=True))(net)
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
                keyphraseness_input,
                pos_tag_input
            ],
            outputs=prediction_layer
        )
        self.model.compile(
            optimizer='adam',
            loss='binary_crossentropy',
            metrics=['acc'],
            sample_weight_mode='temporal')
        self.model.summary()

        train_indices, test_indices = train_test_split(np.arange(len(y)))

        class_counts = np.array(list(dict(sorted(Counter(y_ for y_ in y for y_ in y_).items(), key=lambda x: x[0])).values()))
        class_weights = -np.log(class_counts / np.sum(class_counts))
        sample_weights = [[class_weights[int(y_)] for y_ in y[i]] for i in train_indices]
        sample_weights = pad_sequences(sample_weights, maxlen=max(map(len, x)), dtype=np.float32)

        x_glove = pad_sequences(self.glove_tokenizer.transform(x))
        x_oov = pad_sequences(self.oov_tokenizer.transform(x))
        x_tfidf = pad_sequences(self.tfidf_model.fit_transform(x), dtype=np.float32)
        x_keyphraseness = pad_sequences(self.keyphraseness_model.fit_transform(x, y), dtype=np.float32)
        x_pos_tags = pad_sequences(self.pos_tag_model.predict(x), dtype=np.float32)
        
        y = np.expand_dims(pad_sequences(y), axis=-1)
        
        callbacks = [EarlyStopping(patience=early_stopping_patience)]

        fit_result = self.model.fit(
            sample_weight=sample_weights,
            epochs=epochs,
            callbacks=callbacks,
            x={
                'tokens_glove': x_glove[train_indices],
                'tokens_oov': x_oov[train_indices],
                'tfidf': x_tfidf[train_indices],
                'keyphraseness': x_keyphraseness[train_indices],
                'pos_tags': x_pos_tags[train_indices]
            },
            y=y[train_indices],
            validation_data=(
                {
                    'tokens_glove': x_glove[test_indices],
                    'tokens_oov': x_oov[test_indices],
                    'tfidf': x_tfidf[test_indices],
                    'keyphraseness': x_keyphraseness[test_indices],
                    'pos_tags': x_pos_tags[test_indices]
                },
                y[test_indices],
            ),
        )

        # evaluation stuff
        eval_y_pred_raw = self.model.predict({
            'tokens_glove': x_glove[test_indices],
            'tokens_oov': x_oov[test_indices],
            'tfidf': x_tfidf[test_indices],
            'keyphraseness': x_keyphraseness[test_indices],
            'pos_tags': x_pos_tags[test_indices]
        }).squeeze(axis=-1)
        
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

        x_glove = pad_sequences(self.glove_tokenizer.transform(x))
        x_oov = pad_sequences(self.oov_tokenizer.transform(x))
        x_tfidf = pad_sequences(self.tfidf_model.transform(x), dtype=np.float32)
        x_keyphraseness = pad_sequences(self.keyphraseness_model.transform(x), dtype=np.float32)
        x_pos_tags = pad_sequences(self.pos_tag_model.predict(x), dtype=np.float32)

        y = self.model.predict({
            'tokens_glove': x_glove,
            'tokens_oov': x_oov,
            'tfidf': x_tfidf,
            'keyphraseness': x_keyphraseness,
            'pos_tags': x_pos_tags
        }).squeeze(0).squeeze(-1)

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
            package.writestr('glove_tokenizer.bin', pickle.dumps(self.glove_tokenizer))
            package.writestr('oov_tokenizer.bin', pickle.dumps(self.oov_tokenizer))
            package.writestr('pos_tag_model.bin', pickle.dumps(self.pos_tag_model))
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
            self.pos_tag_model = pickle.loads(package.read('pos_tag_model.bin'))
            self.tfidf_model = pickle.loads(package.read('tfidf_model.bin'))
            self.keyphraseness_model = pickle.loads(package.read('keyphraseness_model.bin'))
            self.evaluation = pickle.loads(package.read('evaluation.bin'))
            self.settings = pickle.loads(package.read('settings.bin'))
        return self
