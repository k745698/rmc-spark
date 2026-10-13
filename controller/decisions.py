"""Explainable decision log: every detection, failover, retry and keep-decision with its reason."""
from __future__ import annotations

import json
import os
import threading
import time


class DecisionLog:
    def __init__(self, path: str | None):
        self.path = path
        self.recent = []
        self._lock = threading.Lock()
        if path:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

    def log(self, kind: str, **fields) -> dict:
        ts = fields.pop("ts", None)
        rec = {"ts": time.time() if ts is None else ts, "kind": kind, **fields}
        with self._lock:
            self.recent.append(rec)
            self.recent = self.recent[-500:]
            if self.path:
                with open(self.path, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(rec, default=str) + "\n")
        return rec
