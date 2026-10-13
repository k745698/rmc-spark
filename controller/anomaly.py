"""Online anomaly scoring for monitoring signals (C1).

EWMA mean/variance with a z-score (Eq. 7):  z_t = (x_t - mu_{t-1}) / sigma_{t-1}
The z-score is mapped to an anomaly level a in [0, 1] with a linear ramp between z_low and z_high.
Anomalous samples are not absorbed into the baseline, so a long fault cannot "become normal".
"""
from __future__ import annotations

import math


def ramp(x: float, low: float, high: float) -> float:
    if x <= low:
        return 0.0
    if x >= high:
        return 1.0
    return (x - low) / (high - low)


class EwmaZScore:
    def __init__(self, alpha: float = 0.2, warmup: int = 5, min_sigma: float = 1e-3):
        self.alpha = alpha
        self.warmup = warmup
        self.min_sigma = min_sigma
        self.mean = 0.0
        self.var = 0.0
        self.n = 0

    def score(self, x: float) -> float:
        """z-score of x against the current baseline (0 during warm-up)."""
        if self.n < self.warmup:
            return 0.0
        sigma = max(math.sqrt(self.var), self.min_sigma, 0.05 * abs(self.mean))
        return (x - self.mean) / sigma

    def update(self, x: float, z_gate: float | None = None) -> float:
        z = self.score(x)
        if z_gate is not None and self.n >= self.warmup and abs(z) >= z_gate:
            return z  # outlier: do not learn from it
        if self.n == 0:
            self.mean, self.var = x, 0.0
        else:
            diff = x - self.mean
            incr = self.alpha * diff
            self.mean += incr
            self.var = (1 - self.alpha) * (self.var + diff * incr)
        self.n += 1
        return z
