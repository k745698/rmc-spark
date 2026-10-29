"""Compute every measured value used in the manuscript from the raw experiment files.

    python paper/results_data.py          -> paper/results.json  (+ printed summary)

Rules (stated in Section XIII of the paper):
  * a run configured with a fault but whose job finished before the fault time (no t_fault) is NOT a
    fault run; it is counted as an additional clean run of its configuration;
  * downtime of a failed run = t_end - t_fault; of a successful fault run = max(0, duration - clean median);
  * run availability = 1 - downtime / duration.
"""
from __future__ import annotations

import glob
import json
import math
import os
import re
from statistics import median

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "results", "raw")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results.json")
SYSTEMS = ["B1_vanilla", "B2_fixed_ckpt", "B3_naive_ha", "P_rmc"]
LABEL = {"B1_vanilla": "B1 Vanilla Spark", "B2_fixed_ckpt": "B2 Fixed checkpoint", "B3_naive_ha": "B3 Naive HA",
         "P_rmc": "P RMC-Spark"}


def events(raw_dir, job_id):
    p = os.path.join(raw_dir, "events", f"{job_id}.jsonl")
    if not os.path.exists(p):
        return []
    out = []
    for line in open(p, encoding="utf-8"):
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return out


def fisher_two_sided(a, b, c, d):
    """Fisher exact test for [[a, b], [c, d]] (two-sided, sum of tables as or less likely)."""
    def p(x):
        r1, c1, n = a + b, a + c, a + b + c + d
        return math.comb(c1, x) * math.comb(n - c1, r1 - x) / math.comb(n, r1)
    r1, c1 = a + b, a + c
    lo, hi = max(0, r1 + c1 - (a + b + c + d)), min(r1, c1)
    p0 = p(a)
    return min(1.0, sum(p(x) for x in range(lo, hi + 1) if p(x) <= p0 + 1e-12))


def main():
    r = pd.read_csv(os.path.join(RAW, "minimum", "runs.csv"))
    r["injected"] = r["t_fault"].notna()
    n_total, n_fault_cfg = len(r), int((r.fault != "none").sum())
    n_not_trig = int(((r.fault != "none") & ~r.injected).sum())
    r = r[(r.fault == "none") | r.injected].copy()      # runs whose fault never fired are excluded
    r["eff_fault"] = r["fault"]
    r["ok"] = (r["state"] == "SUCCEEDED").astype(int)
    clean_med = r[(r.eff_fault == "none") & (r.ok == 1)].groupby("system")["duration_s"].median().to_dict()
    b1 = clean_med["B1_vanilla"]

    def downtime(row):
        if row.eff_fault == "none":
            return 0.0
        if not row.ok:
            return row.t_end - row.t_fault
        return max(0.0, row.duration_s - clean_med[row.system])
    r["downtime_s"] = r.apply(downtime, axis=1)
    r["availability"] = 1 - r["downtime_s"] / r["duration_s"]
    r["detect_s"] = r["t_detect"] - r["t_fault"]
    r["action_s"] = r["t_action"] - r["t_fault"]

    rec = []
    for jid, ef in zip(r.job_id, r.eff_fault):
        ev = events(os.path.join(RAW, "minimum"), jid)
        seen, redo, ck = set(), 0.0, 0
        for e in ev:
            if e.get("event") == "stage_completed":
                if e["stage"] in seen:
                    redo += float(e.get("compute_s") or 0)
                seen.add(e["stage"])
                ck += 1 if e.get("checkpoint") else 0
        rec.append((redo, ck))
    r["recomputed_s"] = [x[0] for x in rec]
    r["checkpoints"] = [x[1] for x in rec]

    cells = {}
    for (s, f), g in r.groupby(["system", "eff_fault"]):
        cells[f"{s}|{f}"] = {
            "system": s, "fault": f, "n": int(len(g)), "succeeded": int(g.ok.sum()),
            "median_duration_s": round(float(g.duration_s.median()), 1),
            "median_downtime_s": round(float(g.downtime_s.median()), 1),
            "median_detect_s": None if g.detect_s.isna().all() else round(float(g.detect_s.median()), 1),
            "median_action_s": None if g.action_s.isna().all() else round(float(g.action_s.median()), 1),
            "mean_recomputed_s": round(float(g.recomputed_s.mean()), 1),
            "mean_availability": round(float(g.availability.mean()), 3),
            "durations": [round(float(x), 1) for x in g.duration_s],
        }

    faulty = r[r.eff_fault != "none"]
    systems = {}
    for s in SYSTEMS:
        g = faulty[faulty.system == s]
        out_g = g[g.eff_fault == "cluster_outage"]
        systems[s] = {
            "label": LABEL[s], "clean_median_s": round(clean_med[s], 1),
            "clean_overhead_vs_B1": round((clean_med[s] - b1) / b1, 3),
            "clean_runs": int(((r.system == s) & (r.eff_fault == "none")).sum()),
            "fault_runs": int(len(g)), "fault_success": int(g.ok.sum()),
            "fault_success_rate": round(float(g.ok.mean()), 3) if len(g) else None,
            "mean_availability": round(float(g.availability.mean()), 3) if len(g) else None,
            "median_downtime_s": round(float(g.downtime_s.median()), 1) if len(g) else None,
            "outage_runs": int(len(out_g)), "outage_success": int(out_g.ok.sum()),
            "outage_max_downtime_s": round(float(out_g.downtime_s.max()), 1) if len(out_g) else None,
            "outage_mean_recomputed_s": round(float(out_g.recomputed_s.mean()), 1) if len(out_g) else None,
            "checkpoints_per_clean_run": round(float(r[(r.system == s) & (r.eff_fault == "none")].checkpoints.mean()), 1),
        }

    # Fisher exact: completion under cluster outage, failover-capable (B3, P) vs not (B1, B2)
    o = r[r.eff_fault == "cluster_outage"]
    cap, nocap = o[o.system.isin(["B3_naive_ha", "P_rmc"])], o[o.system.isin(["B1_vanilla", "B2_fixed_ckpt"])]
    p_cap = fisher_two_sided(int(cap.ok.sum()), int(len(cap) - cap.ok.sum()), int(nocap.ok.sum()), int(len(nocap) - nocap.ok.sum()))
    pP = o[o.system == "P_rmc"]
    p_P = fisher_two_sided(int(pP.ok.sum()), int(len(pP) - pP.ok.sum()), int(nocap.ok.sum()), int(len(nocap) - nocap.ok.sum()))

    # stage timings of the clean ETL runs (for Sections VII/IX)
    stage_times = {}
    for jid in r[(r.eff_fault == "none") & (r.system == "B1_vanilla")].job_id:
        for e in events(os.path.join(RAW, "minimum"), jid):
            if e.get("event") == "stage_completed":
                stage_times.setdefault(e["stage"], []).append(float(e["compute_s"]))
    stage_med = {k: round(median(v), 1) for k, v in stage_times.items()}

    # utilisation / health time series for Fig 23: first P_rmc outage run
    ts = pd.read_csv(os.path.join(RAW, "minimum", "cluster_timeseries.csv"))
    ex = r[(r.system == "P_rmc") & (r.eff_fault == "cluster_outage")].iloc[0]
    w = ts[(ts.ts >= ex.t_submit - 5) & (ts.ts <= ex.t_end + 10)].copy()
    w["t"] = (w.ts - ex.t_submit).round(1)
    w["util"] = (w.cores_used / w.cores.where(w.cores > 0)).fillna(0).round(3)
    series = {c: g[["t", "util", "health"]].values.tolist() for c, g in w.groupby("cluster")}

    # whole-experiment utilisation (Eq. 1)
    util = {}
    for c, g in ts.groupby("cluster"):
        g = g.sort_values("ts")
        dt = g.ts.diff().shift(-1).fillna(0)
        util[c] = round(float((g.cores_used * dt).sum() / (g.cores * dt).sum()), 3)

    # case studies
    cases = pd.read_csv(os.path.join(RAW, "cases", "runs.csv"))
    case_out = {}
    for _, c in cases.iterrows():
        metric = None
        logs = sorted(glob.glob(os.path.join(RAW, "cases", "logs", f"{c.job_id}.a*.log")))
        for lp in logs:
            m = re.search(r"METRICS (\{.*\})", open(lp, encoding="utf-8", errors="replace").read())
            if m:
                metric = eval(m.group(1), {"__builtins__": {}})  # dict literal printed by the job
        evs = events(os.path.join(RAW, "cases"), c.job_id)
        restored = sorted({e["stage"] for e in evs if e.get("event") == "stage_restored"})
        case_out[f"{c.workload}|{c.fault}"] = {
            "workload": c.workload, "fault": c.fault, "state": c.state, "clusters": c.clusters,
            "duration_s": round(float(c.duration_s), 1), "attempts": int(c.attempts),
            "detect_s": None if pd.isna(c.t_detect) else round(float(c.t_detect - c.t_fault), 1),
            "action_s": None if pd.isna(c.t_action) or pd.isna(c.t_fault) else round(float(c.t_action - c.t_fault), 1),
            "metrics": metric, "restored_stages": restored,
        }

    # decision-log excerpt for Section XI
    dec = [json.loads(l) for l in open(os.path.join(RAW, "minimum", "decisions.jsonl"), encoding="utf-8")]
    ex_dec = [d for d in dec if d.get("job_id") == ex.job_id or (d["kind"] == "transition" and d.get("cluster") == "A"
                                                                and ex.t_fault <= d["ts"] <= ex.t_end and d.get("detector") == "health")]
    excerpt = [{"t": round(d["ts"] - ex.t_fault, 1), "kind": d["kind"],
                "text": d.get("reason") or d.get("outcome") or d.get("state") or ""} for d in ex_dec]

    calib = pd.read_csv(os.path.join(RAW, "calibration", "runs.csv")) if os.path.exists(os.path.join(RAW, "calibration", "runs.csv")) else None
    with open(os.path.join(RAW, "minimum", "experiment.json"), encoding="utf-8") as fh:
        exp = json.load(fh)["experiment"]

    res = {
        "n_runs": int(n_total), "n_valid": int(len(r)), "n_fault_configured": n_fault_cfg,
        "n_fault_injected": int(r.injected.sum()), "n_not_triggered": n_not_trig,
        "table12": pd.read_csv(os.path.join(ROOT, "results", "report", "Table 12 Comparative Benchmark Analysis.csv")).set_index("system").to_dict("index"),
        "experiment": exp, "clean_median_s": {k: round(v, 1) for k, v in clean_med.items()},
        "cells": cells, "systems": systems,
        "fisher_p_failover_capable_vs_not": round(p_cap, 4), "fisher_p_P_vs_B1B2": round(p_P, 4),
        "stage_median_s": stage_med, "utilisation": util,
        "fig23": {"job": ex.job_id, "t_fault": round(ex.t_fault - ex.t_submit, 1),
                  "t_action": round(ex.t_action - ex.t_submit, 1), "t_end": round(ex.t_end - ex.t_submit, 1),
                  "series": series},
        "cases": case_out, "decision_excerpt": excerpt,
        "calibration_durations": None if calib is None else [round(float(x), 1) for x in calib.duration_s],
        "first_clean_runs": [round(float(x), 1) for x in r[r.eff_fault == "none"].sort_values("t_submit").duration_s.head(4)],
    }
    json.dump(res, open(OUT, "w", encoding="utf-8"), indent=1)
    for k in ["n_runs", "n_fault_configured", "n_fault_injected", "n_not_triggered", "clean_median_s",
              "fisher_p_failover_capable_vs_not", "fisher_p_P_vs_B1B2", "stage_median_s", "utilisation",
              "calibration_durations", "first_clean_runs"]:
        print(k, res[k])
    for s, v in systems.items():
        print(s, v)
    for k, v in cells.items():
        print(k, {x: v[x] for x in ("n", "succeeded", "median_duration_s", "median_downtime_s", "median_detect_s", "median_action_s", "mean_recomputed_s", "mean_availability")})
    for k, v in case_out.items():
        print(k, v)
    for d in excerpt:
        print(d)


if __name__ == "__main__":
    main()
