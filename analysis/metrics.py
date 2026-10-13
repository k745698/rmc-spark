"""Metric definitions (Section 14 / Table 10). Pure-Python cores + a pandas loader.

Per run
  duration_s            submit -> job end (Eq. 5 uses it)
  delay_s               duration_s - median clean duration of the same system+workload
  overhead              (clean duration of system - clean duration of B1) / clean duration of B1   (Eq. 5)
  detection_s           t_detect - t_fault          (failure detection latency)
  failover_s            t_action - t_fault          (fault -> new driver submitted)
  downtime_s            t_end - t_fault if the job failed, else max(0, delay_s)
  availability          1 - downtime_s / duration_s (Eq. 1, run level)
  recomputed_s          compute time spent redoing stages already completed by an earlier attempt
  checkpoint_s          total time spent writing checkpoints
  stream_recovery_s     streaming: fault -> throughput back to >= 85% of the pre-fault mean and
                        staying there for 40 s (same rule as Vogel et al., DEBS 2024)
Cluster level
  utilisation U = sum(cores_used * dt) / sum(cores * dt)   (Eq. 6)
"""
from __future__ import annotations

import glob
import json
import os
from statistics import median


# ----------------------------------------------------------------------------- events
def load_events(events_dir: str) -> dict:
    """job_id -> list of event dicts (sorted by time)."""
    out = {}
    for path in glob.glob(os.path.join(events_dir, "*.jsonl")):
        evs = []
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                try:
                    evs.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        evs.sort(key=lambda e: e["ts"])
        out[os.path.basename(path)[:-6]] = evs
    return out


def recomputed_work(events: list) -> float:
    """Seconds of stage compute repeated by later attempts (work lost to failures)."""
    seen, redo = set(), 0.0
    for e in events:
        if e.get("event") != "stage_completed":
            continue
        key = e["stage"]
        if key in seen:
            redo += float(e.get("compute_s", 0.0))
        seen.add(key)
    return redo


def checkpoint_time(events: list) -> tuple[float, int]:
    ws = [float(e.get("write_s", 0.0)) for e in events if e.get("event") == "stage_completed" and e.get("checkpoint")]
    return sum(ws), len(ws)


def stream_recovery(events: list, t_fault: float, baseline_window_s: float = 60.0,
                    threshold: float = 0.85, hold_s: float = 40.0) -> float | None:
    """Fault -> first time the processed-rows/s is >= threshold*baseline for hold_s seconds."""
    batches = [(e["ts"], float(e.get("processed_rps", 0.0))) for e in events if e.get("event") == "batch_progress"]
    pre = [r for t, r in batches if t_fault - baseline_window_s <= t < t_fault and r > 0]
    if not pre:
        return None
    base = sum(pre) / len(pre)
    post = [(t, r) for t, r in batches if t >= t_fault]
    start = None
    for t, r in post:
        if r >= threshold * base:
            if start is None:
                start = t
            if t - start >= hold_s:
                return start - t_fault
        else:
            start = None
    return None


def utilisation(rows: list, cluster: str | None = None) -> float | None:
    """rows: dicts with ts, cluster, cores, cores_used (cluster_timeseries.csv)."""
    rows = [r for r in rows if cluster is None or r["cluster"] == cluster]
    by_cluster = {}
    for r in rows:
        by_cluster.setdefault(r["cluster"], []).append(r)
    num = den = 0.0
    for rs in by_cluster.values():
        rs.sort(key=lambda r: float(r["ts"]))
        for a, b in zip(rs, rs[1:]):
            dt = float(b["ts"]) - float(a["ts"])
            num += float(a["cores_used"]) * dt
            den += float(a["cores"]) * dt
    return num / den if den > 0 else None


def availability(duration_s: float, downtime_s: float) -> float:
    return max(0.0, 1.0 - downtime_s / duration_s) if duration_s > 0 else 0.0


def steady_state_availability(mtbf_s: float, mttr_s: float) -> float:
    return mtbf_s / (mtbf_s + mttr_s)


# ----------------------------------------------------------------------------- pandas layer
def load_runs(raw_dir: str):
    import pandas as pd
    runs = pd.read_csv(os.path.join(raw_dir, "runs.csv"))
    runs = runs[runs["state"] != "RUNNER_ERROR"].copy()
    events = load_events(os.path.join(raw_dir, "events"))
    ok = runs["state"] == "SUCCEEDED"

    clean = runs[(runs["fault"] == "none") & ok].groupby(["system", "workload"])["duration_s"].median()
    runs["clean_median_s"] = [clean.get((s, w)) for s, w in zip(runs["system"], runs["workload"])]
    runs["delay_s"] = runs["duration_s"] - runs["clean_median_s"]
    runs["detection_s"] = runs["t_detect"] - runs["t_fault"]
    runs["failover_s"] = runs["t_action"] - runs["t_fault"]
    runs["downtime_s"] = [
        (te - tf) if st != "SUCCEEDED" else max(0.0, d if d == d else 0.0)
        for te, tf, st, d in zip(runs["t_end"], runs["t_fault"].fillna(runs["t_end"]), runs["state"], runs["delay_s"])
    ]
    runs.loc[runs["fault"] == "none", "downtime_s"] = 0.0
    runs["availability"] = [availability(d, dt) for d, dt in zip(runs["duration_s"], runs["downtime_s"])]
    runs["success"] = ok.astype(int)

    rec, ck, nck, srec = [], [], [], []
    for jid, tf, wl in zip(runs["job_id"], runs["t_fault"], runs["workload"]):
        evs = events.get(jid, [])
        rec.append(recomputed_work(evs))
        c, n = checkpoint_time(evs)
        ck.append(c)
        nck.append(n)
        srec.append(stream_recovery(evs, tf) if wl == "streaming" and tf == tf and tf is not None else None)
    runs["recomputed_s"], runs["checkpoint_s"], runs["checkpoints"] = rec, ck, nck
    runs["stream_recovery_s"] = srec

    b1_clean = runs[(runs["system"] == "B1_vanilla") & (runs["fault"] == "none") & ok] \
        .groupby("workload")["duration_s"].median()
    runs["overhead"] = [(c - b1_clean.get(w)) / b1_clean.get(w) if b1_clean.get(w) else None
                        for c, w in zip(runs["clean_median_s"], runs["workload"])]
    return runs


def median_or_none(xs):
    xs = [x for x in xs if x is not None]
    return median(xs) if xs else None
