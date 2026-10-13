"""Workload placement across clusters (C4).

  J_k = alpha * load_k + beta * (1 - H_k) + gamma * transfer_k      (Eq. 9)

load_k     = cores_used / cores (1.0 when unknown)
H_k        = current health score
transfer_k = normalised cost of moving the job's data/checkpoints to cluster k
             (0 for all clusters in the testbed, because everything lives in shared MinIO)
FAILED clusters and explicitly excluded clusters are never chosen.
"""
from __future__ import annotations

from dataclasses import dataclass

from .statemachine import FAILED


@dataclass
class ClusterView:
    name: str
    state: str
    health: float
    cores: int
    cores_used: int
    transfer: float = 0.0

    @property
    def load(self) -> float:
        return self.cores_used / self.cores if self.cores > 0 else 1.0


@dataclass
class Placement:
    cluster: str | None
    scores: dict
    reason: str


def place(views: list, alpha: float, beta: float, gamma: float, exclude: tuple = ()) -> Placement:
    scores = {}
    for v in views:
        if v.state == FAILED or v.name in exclude:
            continue
        scores[v.name] = alpha * v.load + beta * (1.0 - v.health) + gamma * v.transfer
    if not scores:
        return Placement(None, {}, "no eligible cluster (all failed or excluded)")
    best = min(sorted(scores), key=lambda k: scores[k])   # sorted() makes ties deterministic
    detail = ", ".join(f"J_{k}={s:.3f}" for k, s in sorted(scores.items()))
    return Placement(best, scores, f"argmin J -> {best} ({detail})")
