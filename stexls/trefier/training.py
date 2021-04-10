from argparse import ArgumentParser
from pathlib import Path
from typing import List, Literal, Union

import pytorch_lightning as pl
import torch
from pytorch_lightning.callbacks import LearningRateMonitor, ModelCheckpoint
from pytorch_lightning.metrics.functional import accuracy, f1
from torch import nn, optim
from torch.functional import Tensor
from torch.nn.modules.loss import BCEWithLogitsLoss

from . import dataset
from .model import Seq2SeqModel


def train(
    experiment_name: str,
    epochs: int = 1,
    batch_size: int = 10,
    learning_rate: float = 1e-4,
    weight_decay: float = 1e-5,
    hidden_size: int = 32,
    bow_embedding_size: int = 10,
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
        bow_size=len(data.preprocess.bow_vectorizer.get_feature_names()),
        bow_embedding_size=bow_embedding_size,
        class_weights=data.class_weights,
        lr=learning_rate,
        weight_decay=weight_decay,
        dropout=dropout,
    ).to(device)
    lr_monitor = LearningRateMonitor()
    checkpoints = ModelCheckpoint(
        checkpoint_dir,
        filename=experiment_name +
        '-epoch:{epoch}-loss:{val_loss:.2f}-f1:{val_f1:.2f}',
        monitor='val_loss',
        mode='min',
        save_last=True,
    )
    assert checkpoints.dirpath is not None
    data.preprocess.save(Path(checkpoints.dirpath) /
                         f'{experiment_name}-preprocess.bin')
    trainer = pl.Trainer(
        gpus=0 if device == 'cpu' else -1,
        max_epochs=epochs,
        callbacks=[checkpoints, lr_monitor],
        stochastic_weight_avg=True,
        track_grad_norm=2,
    )
    trainer.fit(model, data)


class TrainSeq2SeqModule(pl.LightningModule):
    def __init__(
        self,
        epochs: int,
        vocab_size: int,
        word_embedding_size: int,
        gru_hidden_size: int,
        bow_size: int,
        bow_embedding_size: int = 10,
        class_weights: List[float] = None,
        lr: float = 1e-4,
        weight_decay: float = 1e-5,
        num_classes: int = 2,
        dropout: float = 0.1,
    ):
        super().__init__()
        self.save_hyperparameters()
        self.epochs = epochs
        self.lr = lr
        self.weight_decay = weight_decay
        self.num_classes = num_classes
        self.model = Seq2SeqModel(
            vocab_size=vocab_size,
            word_embedding_size=word_embedding_size,
            gru_hidden_size=gru_hidden_size,
            bow_size=bow_size,
            bow_embedding_size=bow_embedding_size,
            num_classes=num_classes,
            dropout=dropout,
        )

        self.criterion: Union[nn.BCEWithLogitsLoss, nn.CrossEntropyLoss]
        if num_classes == 1:
            self.criterion = nn.BCEWithLogitsLoss(
                pos_weight=torch.tensor(class_weights[-1]) if class_weights else None)
        else:
            self.criterion = nn.CrossEntropyLoss(
                torch.tensor(class_weights[-num_classes:]) if class_weights else None)

    def forward(
            self, tokens: Tensor, bow: Tensor, keyphraseness: Tensor, tfidf: Tensor):
        return self.model.forward(tokens, bow, keyphraseness, tfidf)

    def configure_optimizers(self):
        optimizer = optim.Adam(
            self.parameters(), lr=self.lr, weight_decay=self.weight_decay)
        scheduler = optim.lr_scheduler.ReduceLROnPlateau(
            optimizer, mode='min', factor=0.1, patience=10, verbose=True, min_lr=1e-8)
        return [optimizer], {'scheduler': scheduler, 'monitor': 'val_loss', }

    def _step(self, subset: str, batch, index):
        lengths, tokens, bow, key, tfidf, targets = batch
        output_logits, state = self(
            tokens.to(self.device), bow.to(self.device), key.to(self.device), tfidf.to(self.device))
        logit_acc = []
        target_acc = []
        for logits, target, length in zip(output_logits, targets, lengths):
            logit_acc.append(logits[:length].view(-1, self.num_classes))
            target_acc.append(target[:length].flatten())
        logits = torch.cat(logit_acc)
        targets = torch.cat(target_acc).to(self.device)
        if isinstance(self.criterion, BCEWithLogitsLoss):
            targets = targets.float()
        loss = self.criterion(logits, targets)
        if self.num_classes == 1:
            pred = torch.sigmoid(logits.flatten())
        else:
            pred = torch.softmax(logits, -1)
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
    parser.add_argument('--learning-rate', '--lr', type=float, default=1e-4)
    parser.add_argument('--weight-decay', type=float, default=1e-5)
    parser.add_argument('--embedding-size', type=int, default=10)
    parser.add_argument('--hidden-size', type=int, default=32)
    parser.add_argument('--num-workers', type=int, default=4)
    parser.add_argument('--device', nargs='?', const='gpu', default='cpu')
    args = parser.parse_args()
    train(**vars(args))
