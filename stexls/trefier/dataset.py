import multiprocessing
import os
import re
import subprocess
import traceback
from enum import Enum
from pathlib import Path
from typing import Any, Callable, List, Optional, Sequence, Tuple, Union

import pytorch_lightning as pl
from torch.utils.data import random_split
from torch.utils.data.dataloader import DataLoader
from torch.utils.data.dataset import Dataset
from tqdm import tqdm

from ..util.latex.tokenizer import LatexToken, LatexTokenizer
from .preprocessing import PreprocessedDataset, Preprocessor


class Label(Enum):
    TEXT = 0
    DEF = 1
    TREF = 2

    def __bool__(self):
        return self is not Label.TEXT

    def __int__(self) -> int:
        return int(self.value)


class SmglomDataset(Dataset[Tuple[Tuple[str, ...], Tuple[Label, ...]]]):
    @staticmethod
    def envs2label(envs: Sequence[str]) -> Label:
        def_pattern = re.compile(r'[ma]*[dD]r?ef[ivx]+s?')
        if any(map(def_pattern.fullmatch, envs)):
            return Label.DEF
        tref_pattern = re.compile(r'[ma]*[tT]ref[ivx]+s?')
        if any(map(tref_pattern.fullmatch, envs)):
            return Label.TREF
        return Label.TEXT

    def __init__(
            self,
            source_directory: Union[str, Path],
            train: bool,
            download: bool = False,
            url: str = 'https://gl.mathhub.info/smglom',
            show_progress: bool = False,
            git_args: Sequence[str] = ('git', 'clone', '--depth', '1'),
            num_workers: int = None,
            transform: Callable[[str], Any] = None,
            target_transform: Callable[[Label], Any] = None,
    ) -> None:
        super().__init__()
        transform = transform or (lambda x: x)
        target_transform = target_transform or (lambda x: x)
        repositories = [
            'logic',
            'mathsoft',
            'units',
            'computing',
            'IWGS',
            'jukka',
            'gabe',
            'physics',
            'cs',
            'probability',
            'measure-theory',
            'tannakian',
            'categories',
            'theresas-playground',
            'complexity',
            'arithmetics',
            'elliptic-curves',
            'manifolds',
            'numthy',
            'identities',
            'numthyfun',
            'constants',
            'analysis',
            'trigonometry',
            'meta-inf',
            'numbers',
            'primes',
            'linear-algebra',
            'magic',
            'functional-analysis',
            'geometry',
            'topology',
            'calculus',
            'algebra',
            'graphs',
            'sets',
            'mv',
            'chevahir',
            'SMGloM',
        ]
        source_directory = Path(source_directory)
        if train:
            repositories = repositories[len(repositories)//10:]
            if source_directory.name != 'train':
                source_directory = source_directory / 'train'
        else:
            repositories = repositories[:len(repositories)//10]
            if source_directory.name != 'test':
                source_directory = source_directory / 'test'
        if download:
            download_dir = source_directory
            download_dir.mkdir(parents=True, exist_ok=True)
            if show_progress:
                it = tqdm(repositories)
            else:
                it = repositories
            for repo_name in it:
                link = os.path.join(url, repo_name)
                if isinstance(it, tqdm):
                    it.set_description(f'Cloning {link}')
                target_dir: Path = download_dir / repo_name
                if target_dir.exists():
                    continue
                args = (
                    *git_args,
                    link,
                    str(target_dir),
                )
                try:
                    subprocess.call(args)
                except Exception:
                    traceback.print_exc()
        # Buffer files in the source directory
        files = list(source_directory.glob('**/*.tex'))
        # Create members
        self.documents: List[Tuple[str, ...]] = []
        self.targets: List[Tuple[Label, ...]] = []
        # Parse and tokenize all files in parallel
        with multiprocessing.Pool(num_workers) as pool:
            async_it = pool.imap(LatexTokenizer.from_file, files)
            if show_progress:
                async_it = tqdm(async_it, desc='Tokenizing',
                                total=len(files))
            for parser in async_it:
                # Skip on error
                if parser is None:
                    continue
                # Buffer tokens in file
                tokens: List[LatexToken] = list(parser.tokens())
                # Buffer labels in file
                targets = tuple(
                    SmglomDataset.envs2label(token.envs)
                    for token in parser.tokens())
                # Add if a label other than text is found
                if Label.DEF in targets or Label.TREF in targets:
                    self.documents.append(
                        tuple(transform(token.lexeme) for token in tokens))
                    self.targets.append(
                        tuple(target_transform(target) for target in targets))

    def __len__(self):
        return len(self.documents)

    def __getitem__(self, index):
        return self.documents[index], self.targets[index]


class SmglomToCharacters(Dataset[Tuple[Sequence[str], Sequence[Label]]]):
    def __init__(self, smglom: SmglomDataset):
        self.smglom = smglom

    def __len__(self): return len(self.smglom)

    def __getitem__(self, index):
        text, labels = self.smglom[index]
        new_labels = [
            label
            for word, label in zip(text, labels)
            for char in word
        ]
        new_text = [
            char
            for word in text
            for char in word
        ]
        return new_text, new_labels


class SmglomDataModule(pl.LightningDataModule):
    def __init__(
            self,
            batch_size: int,
            num_workers: int = 0,
            max_num_tokens: int = None,
            val_split: float = 0.2,
            data_dir: Union[str, Path] = 'downloads/smglom'):
        super().__init__()
        self.data_dir = Path(data_dir)
        self.batch_size = batch_size
        self.num_workers = num_workers
        self.val_split = val_split
        self.preprocess = Preprocessor(max_num_tokens=max_num_tokens)
        self.is_data_prepared = False

    @staticmethod
    def target_transform(target: Label):
        return target != Label.TEXT

    def prepare_data(self, **kwargs):
        if self.is_data_prepared:
            return
        self.is_data_prepared = True
        data = SmglomDataset(
            self.data_dir, train=True, target_transform=self.target_transform, download=True, **kwargs)
        val_size = int(self.val_split * len(data))
        train_size = len(data) - val_size
        train_data, val_data = random_split(
            data, [train_size, val_size])

        def from_subset_indices(indices):
            return (
                [data.documents[index] for index in indices],
                [data.targets[index] for index in indices],
            )

        train_doc, train_targ = from_subset_indices(train_data.indices)
        self.train_ds: PreprocessedDataset = self.preprocess.fit_transform(
            train_doc, train_targ)
        val_doc, val_targ = from_subset_indices(val_data.indices)
        self.val_ds: PreprocessedDataset = self.preprocess.transform(
            val_doc, val_targ)

        test_data = SmglomDataset(
            self.data_dir, train=False, target_transform=self.target_transform, download=True, **kwargs)
        self.test_ds: PreprocessedDataset = self.preprocess.transform(
            test_data.documents, test_data.targets)

    def setup(self, stage: Optional[str] = None):
        pass

    def collate_fn(self, batch):
        return PreprocessedDataset.collate_fn(batch)

    def train_dataloader(self) -> Any:
        return DataLoader(
            self.train_ds,
            batch_size=self.batch_size,
            shuffle=True,
            num_workers=self.num_workers,
            collate_fn=self.collate_fn)

    def val_dataloader(self) -> Union[DataLoader, List[DataLoader]]:
        return DataLoader(
            self.val_ds,
            batch_size=self.batch_size,
            shuffle=False,
            num_workers=self.num_workers,
            collate_fn=self.collate_fn)

    def test_dataloader(self):
        return DataLoader(
            self.test_ds,
            batch_size=self.batch_size,
            shuffle=False,
            num_workers=self.num_workers,
            collate_fn=self.collate_fn)
