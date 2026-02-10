"""CEGVR package metadata."""

from __future__ import annotations

from importlib import metadata

try:
    __version__ = metadata.version("cegvr")
except (
    metadata.PackageNotFoundError
):  # pragma: no cover - package metadata absent in dev mode
    __version__ = "0.0.0"

__all__ = ["__version__"]
