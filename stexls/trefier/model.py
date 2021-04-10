from typing import Optional, Tuple

import torch
import torch.nn.functional as F
from torch import nn
from torch.functional import Tensor


class Seq2SeqModel(nn.Module):
    def __init__(
        self,
        vocab_size: int,
        word_embedding_size: int,
        gru_hidden_size: int,
        bow_size: int,
        num_classes: int = 1,
        num_pos_tags: int = 0,
        bow_embedding_size: int = 10,
        dropout: float = 0.2,
    ):
        super().__init__()
        self.num_input_features = (
            word_embedding_size  # token embedding
            + num_pos_tags  # pos tags
            + 1  # with_keyphraseness
            + 1  # with_tfidf
            + bow_embedding_size  # from embedding bow_size into bow_embedding_size
        )
        self.num_classes = num_classes
        self.num_pos_tags = num_pos_tags
        self.hidden_size = gru_hidden_size * 2
        self.embedding = nn.Embedding(
            vocab_size, word_embedding_size)
        self.dropout = nn.Dropout(p=dropout)
        self.embed_bow = nn.Linear(bow_size, bow_embedding_size)
        self.features = nn.GRU(
            input_size=self.num_input_features,
            hidden_size=gru_hidden_size,
            num_layers=3,
            batch_first=True,
            bidirectional=True,
            dropout=dropout,
        )
        self.class_score_logits = nn.Sequential(
            nn.BatchNorm1d(gru_hidden_size * 2),
            nn.Linear(gru_hidden_size * 2, gru_hidden_size),
            nn.ReLU(),
            nn.BatchNorm1d(gru_hidden_size),
            nn.Linear(gru_hidden_size, gru_hidden_size),
            nn.ReLU(),
            nn.BatchNorm1d(gru_hidden_size),
            nn.Linear(gru_hidden_size, num_classes),
        )

    def forward(
        self,
        tokens: Tensor,
        bow: Tensor,
        keyphraseness_values: Optional[Tensor] = None,
        tfidf_values: Optional[Tensor] = None,
        state: Optional[Tensor] = None,
    ) -> Tuple[Tensor, Tensor]:
        # Buffer batch size and number of tokens in the input
        batch_size, num_tokens = tokens.shape
        # Embedd the tokens
        embeddings = self.dropout(self.embedding(tokens))
        # Bow embedding
        bow_embedding = self.dropout(F.relu(self.embed_bow(bow)))
        # Create buffer for the gru inputs
        gru_input_features = [
            embeddings,
            tfidf_values,
            keyphraseness_values,
            bow_embedding,
        ]
        # Concat features
        gru_inputs = torch.cat(gru_input_features, dim=2)
        # Let GRU extract features from each sample in the sequence
        gru_outputs, output_state = self.features(gru_inputs, state)
        # Since linear layers do not require a time axis, remove the time axis
        sequential_input = gru_outputs.reshape(
            batch_size * num_tokens, self.hidden_size)
        # Let Linear layers classify each input
        logits = self.class_score_logits(sequential_input)
        # Add the time axis again
        logits = logits.view(batch_size, num_tokens, self.num_classes)
        # Return
        return logits, output_state
