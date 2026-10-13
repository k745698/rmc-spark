"""Checkpoint policies for resilient stages.

Pure Python (no Spark import) so the decision logic is unit-testable.

The adaptive policy uses the classic optimum checkpoint interval:
  Young (1974):  tau* = sqrt(2 * C * M)
  Daly  (2006):  tau* = sqrt(2CM) * [1 + (1/3)sqrt(C/2M) + (1/9)(C/2M)] - C   for C < 2M, else M
where C is the checkpoint write cost (s) and M the mean time between failures (s).
A stage boundary is checkpointed once the work done since the last checkpoint
(i.e. the work that would be lost and recomputed after a failure) reaches tau*.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


def young_interval(cost_s: float, mtbf_s: float) -> float:
    if cost_s <= 0 or mtbf_s <= 0:
        raise ValueError("cost and MTBF must be positive")
    return math.sqrt(2.0 * cost_s * mtbf_s)


def daly_interval(cost_s: float, mtbf_s: float) -> float:
    if cost_s <= 0 or mtbf_s <= 0:
        raise ValueError("cost and MTBF must be positive")
    if cost_s >= 2.0 * mtbf_s:
        return mtbf_s
    r = cost_s / (2.0 * mtbf_s)
    return math.sqrt(2.0 * cost_s * mtbf_s) * (1.0 + math.sqrt(r) / 3.0 + r / 9.0) - cost_s


def expected_lost_work(interval_s: float, cost_s: float) -> float:
    """First-order expected work lost per failure: half an interval plus one checkpoint (Eq. 4)."""
    return interval_s / 2.0 + cost_s


class Ewma:
    """Exponentially weighted moving average with a prior value."""

    def __init__(self, prior: float, alpha: float = 0.3):
        self.value = float(prior)
        self.alpha = alpha
        self.n = 0

    def update(self, x: float) -> float:
        self.value = x if self.n == 0 else self.alpha * x + (1 - self.alpha) * self.value
        self.n += 1
        return self.value


@dataclass
class Decision:
    checkpoint: bool
    reason: str
    interval_s: float | None = None


class CheckpointPolicy:
    name = "base"

    def decide(self, uncheckpointed_work_s: float, write_cost_s: float, force: bool = False) -> Decision:
        raise NotImplementedError


class NeverPolicy(CheckpointPolicy):
    """Vanilla Spark behaviour: rely on lineage recomputation only (baselines B1, B3)."""
    name = "never"

    def decide(self, uncheckpointed_work_s, write_cost_s, force=False):
        if force:
            return Decision(True, "forced by stage")
        return Decision(False, "policy=never")


class AlwaysPolicy(CheckpointPolicy):
    """Fixed checkpointing after every stage (baseline B2)."""
    name = "always"

    def decide(self, uncheckpointed_work_s, write_cost_s, force=False):
        return Decision(True, "policy=always")


class AdaptivePolicy(CheckpointPolicy):
    """Young/Daly interval driven by the controller's online MTBF estimate (proposed, C2)."""
    name = "adaptive"

    def __init__(self, mtbf_s: float, formula: str = "daly", min_work_s: float = 0.0):
        self.mtbf_s = float(mtbf_s)
        self.formula = formula
        self.min_work_s = min_work_s

    def interval(self, write_cost_s: float) -> float:
        cost = max(write_cost_s, 1e-3)
        fn = daly_interval if self.formula == "daly" else young_interval
        return fn(cost, self.mtbf_s)

    def decide(self, uncheckpointed_work_s, write_cost_s, force=False):
        tau = self.interval(write_cost_s)
        if force:
            return Decision(True, "forced by stage", tau)
        if uncheckpointed_work_s < self.min_work_s:
            return Decision(False, f"work {uncheckpointed_work_s:.1f}s < min {self.min_work_s:.1f}s", tau)
        if uncheckpointed_work_s >= tau:
            return Decision(True, f"work {uncheckpointed_work_s:.1f}s >= tau* {tau:.1f}s "
                                  f"(C={write_cost_s:.1f}s, M={self.mtbf_s:.0f}s)", tau)
        return Decision(False, f"work {uncheckpointed_work_s:.1f}s < tau* {tau:.1f}s", tau)


def make_policy(name: str, mtbf_s: float = 900.0) -> CheckpointPolicy:
    if name == "never":
        return NeverPolicy()
    if name == "always":
        return AlwaysPolicy()
    if name in ("adaptive", "daly"):
        return AdaptivePolicy(mtbf_s, formula="daly")
    if name == "young":
        return AdaptivePolicy(mtbf_s, formula="young")
    raise ValueError(f"unknown checkpoint policy: {name}")
