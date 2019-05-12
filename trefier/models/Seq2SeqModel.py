import numpy as np
from keras.models import Sequential
from keras.layers import Embedding, Dense, Dropout, GRU, Bidirectional, InputLayer

from . import ModelPredictionType, Model
from .. import datasets, keywords, tokenization, downloads

class Seq2SeqModel(Model):
    def __init__(self):
        super().__init__(
            prediction_type=ModelPredictionType.PROBABILITIES,
            label_names={0:'text', 1:'keyword'})
    
    def train(self, save_dir='data/', n_jobs=6):
        documents = smglom.load_documents(save_dir='data/', n_jobs=n_jobs)
        X, Y = smglom.parse(documents, binary_labels=True)
        self.tfidf = keywords.TfIdfModel(X)
        self.keyphraseness = keywords.KeyphrasenessModel(X, Y)
        self.tokenizer = tokenization.TexTokenizer()
        self.tokenizer.fit_on_files(X, n_jobs=n_jobs)
        word_index, embedding_matrix, embedding_layer = downloads.glove.load(50, make_keras_layer=True, perform_pca=True, n_components=10)
        self.model = Sequential([
            embedding_layer,
            Bidirectional(GRU(32, dropout=0.1, activation='tanh', return_sequences=True)),
            Bidirectional(GRU(32, dropout=0.1, activation='tanh', return_sequences=True)),
            Bidirectional(GRU(32, dropout=0.1, activation='tanh', return_sequences=True)),
            Dense(128, activation='sigmoid'),
            Dropout(0.5)
            Dense(128, activation='sigmoid'),
            Dropout(0.5)
            Dense(1, activation='sigmoid')
        ])
        self.model.compile(optimizer='Adam', loss='binary_crossentropy', metrics=['acc'])
        self.model.summary()
    
    def predict(self, path_or_tex_document, ignore_tagged_tokens):
        doc = tokenization.TexDocument(path_or_tex_document, lower=True)
        text = doc.lexemes
