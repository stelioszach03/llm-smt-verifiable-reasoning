"""Utilities for deterministic random seeds."""

from __future__ import annotations

import os
import random
from typing import Final

MAX_32_BIT: Final[int] = 2**32 - 1


def seed_everything(seed: int) -> None:
    """Seed the standard library and optional numerical backends."""

    random.seed(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)

    try:
        import numpy as _np  # type: ignore[import-not-found]
    except ModuleNotFoundError:
        pass
    else:
        _np.random.seed(seed)  # type: ignore[call-arg]

    try:
        import torch as _torch  # type: ignore[import-not-found]
    except ModuleNotFoundError:
        pass
    else:
        _torch.manual_seed(seed)  # type: ignore[call-arg]
        if _torch.cuda.is_available():  # type: ignore[attr-defined]
            _torch.cuda.manual_seed_all(seed)  # type: ignore[attr-defined]


def generate_seed() -> int:
    """Return a pseudo-random 32-bit seed."""

    return random.randint(0, MAX_32_BIT)
