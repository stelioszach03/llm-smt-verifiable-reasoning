"""Configuration helpers for experiment ablations."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict

from cegvr.candidate.types import ExperimentArm


@dataclass(frozen=True)
class ExperimentConfig:
    """Runtime feature toggles for the repair loop."""

    use_grammar: bool = True
    use_solver: bool = True
    enable_repair: bool = True
    pipeline: str = "trace"
    arm: ExperimentArm = ExperimentArm.MULTI_UNSAT_CORE_FEEDBACK

    @classmethod
    def from_flags(
        cls,
        *,
        no_grammar: bool = False,
        no_solver: bool = False,
        no_repair: bool = False,
        pipeline: str = "trace",
        arm: str = ExperimentArm.MULTI_UNSAT_CORE_FEEDBACK.value,
    ) -> "ExperimentConfig":
        return cls(
            use_grammar=not no_grammar,
            use_solver=not no_solver,
            enable_repair=not no_repair,
            pipeline=pipeline,
            arm=ExperimentArm(arm),
        )

    def to_dict(self) -> Dict[str, bool | str]:
        payload = asdict(self)
        payload["arm"] = self.arm.value
        return payload


DEFAULT_EXPERIMENT_CONFIG = ExperimentConfig()


__all__ = ["ExperimentConfig", "DEFAULT_EXPERIMENT_CONFIG"]
