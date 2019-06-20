
from keras import models
from keras.layers import *
from keras.preprocessing.sequence import pad_sequences
from keras.callbacks import EarlyStopping

from sklearn.model_selection import train_test_split
from collections import Counter
from zipfile import ZipFile
from tempfile import NamedTemporaryFile
import pickle

from trefier import datasets, keywords, tokenization, downloads
from trefier.misc import Evaluation
from trefier.misc import Cache
from trefier.models.base import Model

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

    def train(self, epochs=50, save_dir='data/', n_jobs=6):
        oov_token = '<oov>'
        math_token = '<math>'
        with Cache(
                '/tmp/documents.bin',
                lambda: datasets.smglom.parse_files(save_dir=save_dir, n_jobs=n_jobs)) as cache:
            documents = cache.data
            print("Cache documents")
        x, y = datasets.smglom.parse_dataset(documents, binary_labels=True)
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
            assert special_token not in self.oov_tokenizer.word_index
            self.oov_tokenizer.word_index[special_token] = len(self.oov_tokenizer.word_index) + 1

        print("oov tokenizer:", len(self.oov_tokenizer.word_index), 'are <oov>')

        # create a tokenizer for word with fixed glove embedding
        self.glove_tokenizer = tokenization.TexTokenizer(oov_token=oov_token, math_token=math_token)
        self.glove_tokenizer.word_index = glove_word_index

        self.tfidf_model = keywords.TfIdfModel(x)
        self.keyphraseness_model = keywords.KeyphrasenessModel(x, y)
        
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

        train_indices, test_indices = train_test_split(np.arange(len(y)))

        class_counts = np.array(list(dict(sorted(Counter(y_ for y_ in y for y_ in y_).items(), key=lambda x: x[0])).values()))
        class_weights = -np.log(class_counts / np.sum(class_counts))
        sample_weights = [[class_weights[int(y_)] for y_ in y[i]] for i in train_indices]
        sample_weights = pad_sequences(sample_weights, maxlen=max(map(len, x)), dtype=np.float32)

        x_glove = pad_sequences(self.glove_tokenizer.tokens_to_sequences(x))
        x_oov = pad_sequences(self.oov_tokenizer.tokens_to_sequences(x))

        x_tfidf = pad_sequences(self.tfidf_model.fit_transform(x), dtype=np.float32)
        x_keyphraseness = pad_sequences(self.keyphraseness_model.fit_transform(x, y), dtype=np.float32)

        y = np.expand_dims(pad_sequences(y), axis=-1)
        
        callbacks = [EarlyStopping(patience=3)]

        fit_result = self.model.fit(
            sample_weight=sample_weights,
            epochs=epochs,
            callbacks=callbacks,
            x={
                'tokens_glove': x_glove[train_indices],
                'tokens_oov': x_oov[train_indices],
                'tfidf': x_tfidf[train_indices],
                'keyphraseness': x_keyphraseness[train_indices]
            },
            y=y[train_indices],
            validation_data=(
                {
                    'tokens_glove': x_glove[test_indices],
                    'tokens_oov': x_oov[test_indices],
                    'tfidf': x_tfidf[test_indices],
                    'keyphraseness': x_keyphraseness[test_indices]
                },
                y[test_indices],
            ),
        )

        # evaluation stuff
        eval_y_pred_raw = self.model.predict({
            'tokens_glove': x_glove[test_indices],
            'tokens_oov': x_oov[test_indices],
            'tfidf': x_tfidf[test_indices],
            'keyphraseness': x_keyphraseness[test_indices]
        }).squeeze(axis=-1)
        
        eval_y_true, eval_y_pred = zip(*[
            (true_, pred_)
            for x_, true_, pred_
            in zip(x_glove[test_indices], y[test_indices].squeeze(axis=-1), np.round(eval_y_pred_raw).astype(int))
            for x_, true_, pred_
            in zip(x_, true_, pred_)
            if x_ != 0 # remove padding
        ])

        self.evaluation = Evaluation(fit_result.history)
        self.evaluation.evaluate(np.array(eval_y_true), np.array(eval_y_pred), classes={0:'text', 1:'keyword'})
    
    def predict(self, path_or_tex_document):
        if not isinstance(path_or_tex_document, tokenization.TexDocument):
            document = tokenization.TexDocument(path_or_tex_document, True, False)
        if not document.success:
            raise Exception("Failed to parse file")
        tokens, offsets, envs = self.glove_tokenizer.tex_files_to_tokens([document], return_offsets_and_envs=True)
        tokens_offsets_envs = [(t, o, e) for t, o, e in zip(tokens[0], offsets[0], envs[0]) if 'OArg' not in e]
        tokens, offsets, envs = zip(*tokens_offsets_envs)
        tokens, offsets, envs = [tokens], [offsets], [envs]
        x_glove = np.array(self.glove_tokenizer.tokens_to_sequences(tokens), dtype=np.int32)
        x_oov = np.array(self.oov_tokenizer.tokens_to_sequences(tokens), dtype=np.int32)
        x_tfidf = np.array(self.tfidf_model.transform(tokens), dtype=np.float32)
        x_keyphraseness = np.array(self.keyphraseness_model.transform(tokens), dtype=np.float32)
        y_pred = self.model.predict({
            'tokens_glove': x_glove,
            'tokens_oov': x_oov,
            'tfidf': x_tfidf,
            'keyphraseness': x_keyphraseness
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
