from __future__ import annotations

from typing import Dict, Hashable, List, Sequence, Tuple


class Vocab:
    def __init__(
            self,
            max_num_tokens: int = None,
            special_tokens: Tuple[Hashable, ...] = (),
            unk: Hashable = '<unk>',
    ) -> None:
        self.max_num_tokens = max_num_tokens
        self.unk = unk
        self.special_tokens = special_tokens
        self.itos: List[Hashable] = []
        self.stoi: Dict[Hashable, int] = {}
        self.counts: Dict[Hashable, int] = {}

    def __len__(self):
        return self.vocab_size()

    def __getitem__(self, index: Hashable) -> int:
        return self.stoi.get(index, self.stoi[self.unk])

    def update_vocab(self, documents: Sequence[Sequence[Hashable]]) -> Vocab:
        for document in documents:
            for token in document:
                self.counts.setdefault(token, 0)
                self.counts[token] += 1

        itos = [self.unk]
        itos.extend(self.special_tokens)
        itos.extend(
            sorted(self.counts, key=lambda x: self.counts[x], reverse=True))
        if self.max_num_tokens is None:
            self.itos = itos
        else:
            self.itos = itos[:self.max_num_tokens]
        self.stoi = {
            tok: i
            for i, tok in enumerate(self.itos)
        }
        return self

    def vocab_size(self) -> int:
        return len(self.stoi)
