"""Reliability accounting and the explainable reliability score (C5).

Per cluster we track up/down intervals (from FAILED transitions), job outcomes and health.

  A_k    = uptime / (uptime + downtime)                                (Eq. 1, measured)
  MTBF_k = (M0 * n0 + uptime) / (n0 + failures)                         (Bayesian-style prior M0)
  R_k    = sum_j w_j s_j,  s = {availability, recovery, success, health}  (Eq. 10)
     recovery = 1 - min(1, MTTR / MTTR_ref)
"""
from __future__ import annotations


class ClusterReliability:
    def __init__(self, name: str, mtbf_prior_s: float, prior_weight: float, start_ts: float):
        self.name = name
        self.m0 = mtbf_prior_s
        self.n0 = prior_weight
        self.uptime = 0.0
        self.downtime = 0.0
        self.failures = 0
        self.repairs = []            # durations of completed outages
        self.jobs_ok = 0
        self.jobs_failed = 0
        self.health_sum = 0.0
        self.health_n = 0
        self._last_ts = start_ts
        self._down = False
        self._down_since = None

    def observe(self, ts: float, failed: bool, health: float) -> None:
        dt = max(0.0, ts - self._last_ts)
        if self._down:
            self.downtime += dt
        else:
            self.uptime += dt
        self._last_ts = ts
        self.health_sum += health
        self.health_n += 1
        if failed and not self._down:
            self._down, self._down_since = True, ts
            self.failures += 1
        elif not failed and self._down:
            self._down = False
            self.repairs.append(ts - self._down_since)

    def record_job(self, ok: bool) -> None:
        if ok:
            self.jobs_ok += 1
        else:
            self.jobs_failed += 1

    @property
    def availability(self) -> float:
        total = self.uptime + self.downtime
        return self.uptime / total if total > 0 else 1.0

    @property
    def mttr(self) -> float | None:
        return sum(self.repairs) / len(self.repairs) if self.repairs else None

    @property
    def mtbf(self) -> float:
        return (self.m0 * self.n0 + self.uptime) / (self.n0 + self.failures)

    def score(self, weights: dict, mttr_ref_s: float) -> dict:
        jobs = self.jobs_ok + self.jobs_failed
        mttr = self.mttr
        parts = {
            "availability": self.availability,
            "recovery": 1.0 if mttr is None else 1.0 - min(1.0, mttr / mttr_ref_s),
            "success": self.jobs_ok / jobs if jobs else 1.0,
            "health": self.health_sum / self.health_n if self.health_n else 1.0,
        }
        total_w = sum(weights[k] for k in parts)
        contrib = {k: weights[k] / total_w * v for k, v in parts.items()}
        return {"cluster": self.name, "R": sum(contrib.values()), "components": parts,
                "contributions": contrib, "mtbf_s": self.mtbf, "mttr_s": mttr,
                "failures": self.failures, "uptime_s": self.uptime, "downtime_s": self.downtime}


def system_mtbf(trackers: list) -> float:
    """Pooled MTBF over all clusters - what the adaptive checkpoint policy receives."""
    if not trackers:
        raise ValueError("no clusters")
    m0, n0 = trackers[0].m0, trackers[0].n0
    up = sum(t.uptime for t in trackers)
    fails = sum(t.failures for t in trackers)
    return (m0 * n0 + up) / (n0 + fails)
