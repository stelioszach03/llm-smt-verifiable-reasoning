"""Configuration helpers for experiment ablations."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict


@dataclass(frozen=True)
class ExperimentConfig:
    """Runtime feature toggles for the repair loop."""

    use_grammar: bool = True
    use_solver: bool = True
    enable_repair: bool = True

    @classmethod
    def from_flags(
        cls,
        *,
        no_grammar: bool = False,
        no_solver: bool = False,
        no_repair: bool = False,
    ) -> "ExperimentConfig":
        return cls(
            use_grammar=not no_grammar,
            use_solver=not no_solver,
            enable_repair=not no_repair,
        )

    def to_dict(self) -> Dict[str, bool]:
        return asdict(self)


DEFAULT_EXPERIMENT_CONFIG = ExperimentConfig()


__all__ = ["ExperimentConfig", "DEFAULT_EXPERIMENT_CONFIG"]
