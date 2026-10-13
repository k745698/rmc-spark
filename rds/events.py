"""Append-only JSONL event log written by the driver and read by the controller/analysis."""
from __future__ import annotations

import json
import os
import time


class EventLog:
    def __init__(self, path: str | None, **context):
        self.path = path
        self.context = context
        if path:
            os.makedirs(os.path.dirname(path), exist_ok=True)

    def emit(self, event: str, **fields) -> dict:
        record = {"ts": time.time(), "event": event, **self.context, **fields}
        if self.path:
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(record) + "\n")
                fh.flush()
        return record


def read_events(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    out = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    pass  # a line cut short by a killed driver
    return out
