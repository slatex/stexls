from pathlib import Path
from argparse import ArgumentParser
from typing import Literal, Union

import pytorch_lightning as pl
import torch
from pytorch_lightning.metrics.functional import accuracy, f1
from pytorch_lightning.callbacks import ModelCheckpoint
from torch import nn, optim
from torch.functional import Tensor

from . import dataset
from .model import Seq2SeqModel


def train(
    experiment_name: str,
    epochs: int = 1,
    batch_size: int = 10,
    lr: float = 1e-4,
    weight_decay: float = 1e-5,
    hidden_size: int = 32,
    embedding_size: int = 10,
    device: Literal['cpu', 'cuda'] = 'cpu',
    num_workers: int = 0,
    val_split: float = 0.2,
    dropout: float = 0.1,
    data_dir: Union[str, Path] = 'downloads/smglom',
    checkpoint_dir: Union[str, Path] = 'checkpoints',
):
    data = dataset.SmglomDataModule(
        batch_size=batch_size,
        num_workers=num_workers,
        val_split=val_split,
        data_dir=data_dir)
    data.prepare_data(show_progress=True)
    model = TrainSeq2SeqModule(
        epochs=epochs,
        vocab_size=len(data.preprocess.vocab),
        word_embedding_size=embedding_size,
        gru_hidden_size=hidden_size,
        lr=lr,
        weight_decay=weight_decay,
        dropout=dropout,
    ).to(device)
    checkpoints = ModelCheckpoint(
        checkpoint_dir,
        filename=experiment_name + '-{epoch}-val:{val_loss:.2f}-{val_f1:.2f}',
        monitor='val_loss',
        mode='min',
    )
    trainer = pl.Trainer(
        gpus=0 if device == 'cpu' else -1,
        max_epochs=epochs,
        callbacks=[checkpoints]
    )
    trainer.fit(model, data)


class TrainSeq2SeqModule(pl.LightningModule):
    def __init__(
        self,
        epochs: int,
        vocab_size: int,
        word_embedding_size: int,
        gru_hidden_size: int,
        lr: float = 1e-4,
        weight_decay: float = 1e-5,
        dropout: float = 0.1,
    ):
        super().__init__()
        self.save_hyperparameters(
            'vocab_size', 'word_embedding_size', 'gru_hidden_size')
        self.epochs = epochs
        self.lr = lr
        self.weight_decay = weight_decay
        self.model = Seq2SeqModel(
            vocab_size=vocab_size,
            word_embedding_size=word_embedding_size,
            gru_hidden_size=gru_hidden_size,
            num_classes=1,
            with_tfidf=True,
            with_keyphraseness=True,
            dropout=dropout,
        )
        self.criterion = nn.BCEWithLogitsLoss()

    def forward(
            self,
            tokens: Tensor,
            keyphraseness: Tensor,
            tfidf: Tensor):
        return self.model.forward(
            tokens.to(self.device),
            keyphraseness.to(self.device),
            tfidf.to(self.device))

    def configure_optimizers(self):
        optimizer = optim.Adam(
            self.parameters(), lr=self.lr, weight_decay=self.weight_decay)
        scheduler = optim.lr_scheduler.ReduceLROnPlateau(
            optimizer, mode='min', factor=0.1, patience=self.epochs, verbose=True, min_lr=1e-7)
        return [optimizer], {'scheduler': scheduler, 'monitor': 'val_loss', }

    def _step(self, subset: str, batch, index):
        lengths, tokens, key, tfidf, targets = batch
        output_logits, state = self(
            tokens, key, tfidf)
        logit_acc = []
        target_acc = []
        for logits, target, length in zip(output_logits, targets, lengths):
            logit_acc.append(logits[:length].flatten())
            target_acc.append(target[:length].flatten())
        logits = torch.cat(logit_acc)
        targets = torch.cat(target_acc)
        loss = self.criterion(logits, targets.float())
        pred = torch.sigmoid(logits)
        self.log_metrics(subset, pred, targets, loss)
        return loss

    def log_metrics(
            self,
            subset: str,
            preds: Tensor,
            targets: Tensor,
            loss: Tensor):
        self.log(f'{subset}_loss', loss, on_epoch=True)
        self.log(f'{subset}_accuracy', accuracy(preds, targets), on_epoch=True)
        self.log(f'{subset}_f1', f1(
            preds, targets, num_classes=1), on_epoch=True)

    def training_step(self, *args, **kwargs):
        return self._step('train', *args, **kwargs)

    def validation_step(self, *args, **kwargs):
        return self._step('val', *args, **kwargs)


if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_argument('--experiment-name', default='test')
    parser.add_argument('--epochs', type=int, default=1)
    parser.add_argument('--batch-size', type=int, default=10)
    parser.add_argument('--lr', type=float, default=1e-4)
    parser.add_argument('--weight-decay', type=float, default=1e-5)
    parser.add_argument('--embedding-size', type=int, default=10)
    parser.add_argument('--hidden-size', type=int, default=32)
    parser.add_argument('--num-workers', type=int, default=4)
    parser.add_argument('--device', nargs='?', const='gpu', default='cpu')
    args = parser.parse_args()
    train(**vars(args))
