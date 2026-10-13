"""Cluster health score with per-signal explanations (C1 + C5).

  H_k = 1 - sum_i w_i * a_{i,k}     (Eq. 8),  a_{i,k} in [0,1],  sum_i w_i = 1

Signals
  unreachable    master UI did not answer the probe
  workers_lost   1 - alive_workers / expected_workers
  latency        EWMA z-score of probe latency (gray failures such as network delay)
  stall          seconds without task progress for a running job / stall_limit
  executor_loss  executors lost by the running job / expected executors
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .anomaly import EwmaZScore, ramp

SIGNALS = ("unreachable", "workers_lost", "latency", "stall", "executor_loss")


@dataclass
class Observation:
    ts: float
    reachable: bool
    latency_s: float = 0.0
    alive_workers: int = 0
    cores: int = 0
    cores_used: int = 0
    stall_s: float = 0.0           # filled in by the job manager (0 when no job runs here)
    executors_lost: int = 0
    executors_expected: int = 0


@dataclass
class HealthReport:
    ts: float
    health: float
    anomalies: dict
    contributions: dict = field(default_factory=dict)
    critical: bool = False

    def top_causes(self, k: int = 2) -> list:
        items = sorted(self.contributions.items(), key=lambda kv: kv[1], reverse=True)
        causes = [(name, round(c, 3)) for name, c in items[:k] if c > 0]
        return ([("no_workers", 1.0)] + causes) if self.critical else causes


class HealthModel:
    def __init__(self, weights: dict, expected_workers: int, alpha: float = 0.2,
                 z_low: float = 3.0, z_high: float = 8.0, stall_limit_s: float = 45.0):
        missing = set(SIGNALS) - set(weights)
        if missing:
            raise ValueError(f"missing health weights: {missing}")
        total = sum(weights[s] for s in SIGNALS)
        self.weights = {s: weights[s] / total for s in SIGNALS}   # normalise to sum 1
        self.expected_workers = max(1, expected_workers)
        self.latency = EwmaZScore(alpha=alpha)
        self.z_low, self.z_high = z_low, z_high
        self.stall_limit_s = stall_limit_s

    def assess(self, obs: Observation) -> HealthReport:
        a = dict.fromkeys(SIGNALS, 0.0)
        if not obs.reachable:
            a["unreachable"] = 1.0
            a["workers_lost"] = 1.0
        else:
            a["workers_lost"] = max(0.0, 1.0 - obs.alive_workers / self.expected_workers)
            z = self.latency.update(obs.latency_s, z_gate=self.z_low)
            a["latency"] = ramp(z, self.z_low, self.z_high)
        a["stall"] = min(1.0, obs.stall_s / self.stall_limit_s) if self.stall_limit_s > 0 else 0.0
        if obs.executors_expected > 0:
            a["executor_loss"] = min(1.0, obs.executors_lost / obs.executors_expected)
        contrib = {s: self.weights[s] * a[s] for s in SIGNALS}
        health = max(0.0, min(1.0, 1.0 - sum(contrib.values())))
        # Hard rule: a reachable master with zero workers has no capacity at all.
        critical = obs.reachable and obs.alive_workers == 0
        if critical:
            health = 0.0
        return HealthReport(ts=obs.ts, health=health, anomalies=a, contributions=contrib,
                            critical=critical)
