"""Per-cluster failure detectors.

HealthStateMachine (proposed):  HEALTHY -> SUSPECT -> FAILED -> HEALTHY with hysteresis
  - SUSPECT  when H < suspect_threshold
  - FAILED   when H < failed_threshold for `failed_consecutive` polls in a row
  - HEALTHY  again only after H >= suspect_threshold for `recovered_consecutive` polls
TimeoutDetector (baseline B3): FAILED when the master was unreachable for `timeout_s`.
"""
from __future__ import annotations

from dataclasses import dataclass

HEALTHY, SUSPECT, FAILED = "HEALTHY", "SUSPECT", "FAILED"
STATE_CODE = {HEALTHY: 0, SUSPECT: 1, FAILED: 2}


@dataclass
class Transition:
    ts: float
    cluster: str
    old: str
    new: str
    reason: str


class HealthStateMachine:
    def __init__(self, cluster: str, suspect_threshold: float, failed_threshold: float,
                 failed_consecutive: int, recovered_consecutive: int):
        if not 0 <= failed_threshold <= suspect_threshold <= 1:
            raise ValueError("need 0 <= failed_threshold <= suspect_threshold <= 1")
        self.cluster = cluster
        self.suspect_t = suspect_threshold
        self.failed_t = failed_threshold
        self.failed_n = failed_consecutive
        self.recovered_n = recovered_consecutive
        self.state = HEALTHY
        self._low = 0
        self._good = 0

    def update(self, ts: float, health: float, causes: str = "") -> Transition | None:
        self._low = self._low + 1 if health < self.failed_t else 0
        self._good = self._good + 1 if health >= self.suspect_t else 0
        old = self.state
        if self.state == FAILED:
            if self._good >= self.recovered_n:
                self.state = HEALTHY
        elif self._low >= self.failed_n:
            self.state = FAILED
        elif health < self.suspect_t:
            self.state = SUSPECT
        else:
            self.state = HEALTHY
        if self.state != old:
            return Transition(ts, self.cluster, old, self.state,
                              f"H={health:.2f} ({causes})" if causes else f"H={health:.2f}")
        return None


class TimeoutDetector:
    def __init__(self, cluster: str, timeout_s: float):
        self.cluster = cluster
        self.timeout_s = timeout_s
        self.state = HEALTHY
        self._down_since = None

    def update(self, ts: float, reachable: bool) -> Transition | None:
        old = self.state
        if reachable:
            self._down_since = None
            self.state = HEALTHY
        else:
            if self._down_since is None:
                self._down_since = ts
            if ts - self._down_since >= self.timeout_s:
                self.state = FAILED
        if self.state != old:
            return Transition(ts, self.cluster, old, self.state,
                              "master reachable" if reachable else f"unreachable >= {self.timeout_s:.0f}s")
        return None
