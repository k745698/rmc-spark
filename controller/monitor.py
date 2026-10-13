"""Probes: Spark master JSON endpoint (cluster level) and driver REST API (job level)."""
from __future__ import annotations

import time

import requests

from .health import Observation


def probe_master(ui_url: str, timeout_s: float) -> Observation:
    t0 = time.time()
    try:
        r = requests.get(f"{ui_url.rstrip('/')}/json/", timeout=timeout_s)
        r.raise_for_status()
        j = r.json()
        return Observation(ts=t0, reachable=j.get("status", "ALIVE") == "ALIVE",
                           latency_s=time.time() - t0,
                           alive_workers=int(j.get("aliveworkers", 0)),
                           cores=int(j.get("cores", 0)), cores_used=int(j.get("coresused", 0)))
    except (requests.RequestException, ValueError):
        return Observation(ts=t0, reachable=False, latency_s=time.time() - t0)


def probe_driver(ui_port: int, timeout_s: float = 1.0) -> dict | None:
    """Task progress of the (single) application served by a driver UI on this host.

    Returns {'completed': int, 'active_execs': int, 'lost_execs': int, 'seen_execs': int}
    or None if the driver UI is not up (yet).
    """
    base = f"http://localhost:{ui_port}/api/v1/applications"
    try:
        apps = requests.get(base, timeout=timeout_s).json()
        if not apps:
            return None
        app_id = apps[0]["id"]
        execs = requests.get(f"{base}/{app_id}/allexecutors", timeout=timeout_s).json()
    except (requests.RequestException, ValueError, KeyError, IndexError):
        return None
    workers = [e for e in execs if e.get("id") != "driver"]
    return {
        "completed": sum(int(e.get("completedTasks", 0)) for e in workers),
        "active_execs": sum(1 for e in workers if e.get("isActive")),
        "lost_execs": sum(1 for e in workers if not e.get("isActive")),
        "seen_execs": len(workers),
    }
