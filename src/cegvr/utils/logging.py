"""Logging helpers built on top of `rich`."""

from __future__ import annotations

import logging
from typing import Final

from rich.logging import RichHandler

DEFAULT_FORMAT: Final[str] = "%(message)s"
DEFAULT_DATE_FORMAT: Final[str] = "[%X]"


def setup_logging(verbosity: int = 0) -> None:
    """Configure application-wide logging output.

    Verbosity levels map to logging levels as follows:
    0 -> WARNING, 1 -> INFO, 2+ -> DEBUG.
    """

    if verbosity <= 0:
        level = logging.WARNING
    elif verbosity == 1:
        level = logging.INFO
    else:
        level = logging.DEBUG

    logging.basicConfig(
        level=level,
        format=DEFAULT_FORMAT,
        datefmt=DEFAULT_DATE_FORMAT,
        handlers=[RichHandler(rich_tracebacks=True)],
        force=True,
    )
