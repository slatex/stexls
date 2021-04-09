from typing import Optional, Sequence, Tuple, Union

import numpy as np
from sklearn.model_selection import train_test_split


def stratify_sequences(
        *arrays: Sequence,
        sequence_of_targets: Sequence[Sequence[int]],
        num_bins: int = 5,
        test_size: Optional[Union[float, int]] = None,
        train_size: Optional[Union[float, int]] = None,
        shuffle: bool = True,
        random_state: Optional[int] = None,
) -> Tuple[Sequence, ...]:
    """ Adapts sklearn.model_selection.train_test_split in order to stratify a sequence of targets
    that are atomic and can't be split.

    This method tries to optimize that the sum of relevant targets in each split is equal, without
    splitting the input sequences apart.

    Args:
        sequence_of_targets (Sequence[Sequence[int]]): The targets for the input arrays.
        num_bins (int, optional): Number of bins used to approximate the distribution of relevant samples.. Defaults to 5.
        test_size (Optional[Union[float, int]], optional): Inherited from train_test_split. Defaults to None.
        train_size (Optional[Union[float, int]], optional): Inherited from train_test_split. Defaults to None.
        shuffle (bool, optional): Inherited from train_test_split. Defaults to True.
        random_state (Optional[int], optional): Inherited from train_test_split. Defaults to None.

    Returns:
        Tuple[Sequence, ...]: Splits the input arrays into train and test subsets.
    """
    sums = np.array([sum(targets) for targets in sequence_of_targets])
    binned_sums = np.digitize(sums, bins=np.linspace(
        sums.min(), sums.max(), num_bins))
    while True:
        bins, counts = np.unique(binned_sums, return_counts=True)
        for i in range(len(counts) - 1, 1, -1):
            if counts[i] > 1:
                continue
            cond = binned_sums == bins[i]
            binned_sums[cond] = bins[i] - 1
            break
        else:
            break
    return train_test_split(
        *arrays,
        test_size=test_size,
        train_size=train_size,
        random_state=random_state,
        shuffle=shuffle,
        stratify=binned_sums)
