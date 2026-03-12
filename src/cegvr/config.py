"""YAML-backed configuration loader for the CEGVR toolkit."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from typing import Literal

import yaml
from pydantic import BaseModel, Field, ValidationError

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "configs" / "default.yaml"


class AppSettings(BaseModel):
    """Metadata about the running application."""

    name: str = "CEGVR"
    description: str | None = None
    seed: int = Field(ge=0, default=2024)


class LoggingSettings(BaseModel):
    """Basic logging configuration."""

    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"


class DatasetSettings(BaseModel):
    """Dataset definition used by demo commands."""

    path: Path = Field(..., description="Path to the dataset file.")
    description: str | None = None


class AppConfig(BaseModel):
    """Top-level configuration container."""

    app: AppSettings = AppSettings()
    logging: LoggingSettings = LoggingSettings()
    dataset: DatasetSettings | None = None

    def resolve_paths(self, base_path: Path) -> "AppConfig":
        """Return a copy of the config with relative paths resolved."""

        if self.dataset is None:
            return self
        dataset = self.dataset
        if dataset.path.is_absolute():
            return self
        resolved_dataset = dataset.model_copy(
            update={"path": (base_path / dataset.path).resolve()}
        )
        return self.model_copy(update={"dataset": resolved_dataset})

    def yaml(self) -> str:
        """Render the configuration as YAML for display."""

        # `mode="json"` coerces Path/datetime/Enum into JSON-safe scalars,
        # which safe_dump can then represent. `mode="python"` leaves
        # PosixPath instances in the dict and crashes the representer.
        return yaml.safe_dump(self.model_dump(mode="json"), sort_keys=False)


def load_config(path: Path | str | None = None) -> AppConfig:
    """Load configuration from a YAML file and validate it."""

    target = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    if not target.exists():
        raise FileNotFoundError(f"Configuration file not found: {target}")

    with target.open("r", encoding="utf-8") as handle:
        payload: dict[str, Any] | None = yaml.safe_load(handle)

    raw = payload or {}
    try:
        config = AppConfig.model_validate(raw)
    except ValidationError as exc:
        raise ValueError(f"Invalid configuration: {exc}") from exc

    return config.resolve_paths(target.parent)


__all__ = [
    "AppConfig",
    "AppSettings",
    "LoggingSettings",
    "DatasetSettings",
    "DEFAULT_CONFIG_PATH",
    "load_config",
]
