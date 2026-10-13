"""Collect every measured result into one paper-ready Markdown file.

    docker compose exec controller python -m scripts.collect_results results/raw/full --out RESULTS_FOR_PAPER.md

Reads  <raw_dir>/runs.csv, events/, decisions.jsonl, cluster_timeseries.csv, experiment.json,
       results/report/*.md (from analysis.report), results/logs/pytest_*.txt, results/demo/*.txt
Writes one Markdown file: provenance, the value for every [[placeholder]] in paper/content/06_results.txt,
hypothesis verdicts H1-H5 with tests, ablation pairs, continuity matrix, reliability scores, tables, figures.
Every number comes from the raw files; nothing is typed in by hand.
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import math
import os

import pandas as pd

from analysis.metrics import load_events, load_runs
from analysis.stats import bootstrap_ci, cliffs_delta, magnitude, mann_whitney
from controller.reliability import ClusterReliability

ORDER = ["B1_vanilla", "B2_fixed_ckpt", "B3_naive_ha", "A1_rmc_no_adapt", "P_rmc"]
SHORT = {"B1_vanilla": "B1", "B2_fixed_ckpt": "B2", "B3_naive_ha": "B3", "A1_rmc_no_adapt": "A1", "P_rmc": "P"}
FAILOVER_FAULTS = ["cluster_outage", "network_partition"]


def f(v, nd=1, unit=""):
    """Format a number, or 'n/a' when missing."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "n/a"
    if isinstance(v, (int,)) and not isinstance(v, bool):
        return f"{v}{unit}"
    return f"{float(v):.{nd}f}{unit}"


def pct(v):
    return "n/a" if v is None or (isinstance(v, float) and math.isnan(v)) else f"{100 * float(v):.0f} %"


def pval(p):
    return "n/a (n<2 per group)" if p is None else (f"{p:.2g}" if p >= 0.001 else "<0.001")


def systems(df):
    present = set(df["system"])
    return [s for s in ORDER if s in present] + sorted(present - set(ORDER))


def load_decisions(path):
    out = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return out


def sub(df, **kw):
    for k, v in kw.items():
        df = df[df[k].isin(v)] if isinstance(v, (list, tuple, set)) else df[df[k] == v]
    return df


def med(s):
    s = pd.to_numeric(s, errors="coerce").dropna()
    return float(s.median()) if len(s) else None


def mean(s):
    s = pd.to_numeric(s, errors="coerce").dropna()
    return float(s.mean()) if len(s) else None


def lst(s):
    return [float(x) for x in pd.to_numeric(s, errors="coerce").dropna()]


def md_table(header, rows):
    out = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out) + "\n"


def compare(a, b, name_a, name_b, metric="downtime_s", runs=None):
    xa, xb = lst(a[metric]), lst(b[metric])
    d = cliffs_delta(xa, xb)
    return {"a": name_a, "b": name_b, "n_a": len(xa), "n_b": len(xb), "med_a": med(a[metric]),
            "med_b": med(b[metric]), "p": mann_whitney(xa, xb), "delta": d,
            "mag": magnitude(d) if d == d else "n/a"}


def cmp_text(c, unit="s"):
    return (f"median {f(c['med_a'])} {unit} ({SHORT.get(c['a'], c['a'])}, n={c['n_a']}) vs "
            f"{f(c['med_b'])} {unit} ({SHORT.get(c['b'], c['b'])}, n={c['n_b']}); Mann-Whitney p = {pval(c['p'])}, "
            f"Cliff's δ = {f(c['delta'], 2)} ({c['mag']})")


def replay_reliability(ts_path, runs, cfg_ctl):
    """Rebuild each cluster's reliability score R from the recorded timeseries + job outcomes."""
    if not os.path.exists(ts_path):
        return {}
    ts = pd.read_csv(ts_path).sort_values("ts")
    if ts.empty:
        return {}
    trackers = {}
    for c, g in ts.groupby("cluster"):
        tr = ClusterReliability(c, cfg_ctl.get("mtbf_prior_s", 900.0), cfg_ctl.get("mtbf_prior_weight", 1.0),
                                float(g["ts"].iloc[0]))
        for t, st, h in zip(g["ts"], g["state_smart"], g["health"]):
            tr.observe(float(t), st == "FAILED", float(h))
        trackers[c] = tr
    for _, r in runs.iterrows():   # job outcome is credited to the cluster the job ended on
        last = str(r.get("clusters") or "").split(">")[-1]
        if last in trackers:
            trackers[last].record_job(r["state"] == "SUCCEEDED")
    w = cfg_ctl.get("reliability_weights", {"availability": 0.4, "recovery": 0.2, "success": 0.2, "health": 0.2})
    return {c: t.score(w, cfg_ctl.get("mttr_reference_s", 120.0)) for c, t in trackers.items()}


def driver_startup(runs, events):
    """Failover runs: time from the failover decision (t_action) to the new attempt's first event."""
    out = []
    for _, r in runs.iterrows():
        if not (r["failovers"] and r["t_action"] == r["t_action"]):
            continue
        evs = [e for e in events.get(r["job_id"], []) if e.get("event") == "attempt_started"
               and e["ts"] >= r["t_action"]]
        if evs:
            out.append(evs[0]["ts"] - r["t_action"])
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("raw_dir")
    p.add_argument("--report", default="results/report")
    p.add_argument("--out", default="RESULTS_FOR_PAPER.md")
    a = p.parse_args()

    runs_all = pd.read_csv(os.path.join(a.raw_dir, "runs.csv"))
    runs = load_runs(a.raw_dir)
    events = load_events(os.path.join(a.raw_dir, "events"))
    decisions = load_decisions(os.path.join(a.raw_dir, "decisions.jsonl"))
    exp = {}
    if os.path.exists(os.path.join(a.raw_dir, "experiment.json")):
        with open(os.path.join(a.raw_dir, "experiment.json"), encoding="utf-8") as fh:
            exp = json.load(fh)
    ctl = (exp.get("cluster_config") or {}).get("controller", {})
    faulty = runs[runs["fault"] != "none"]
    clean = runs[runs["fault"] == "none"]
    S = systems(runs)
    L = []   # output lines
    w = L.append

    # ------------------------------------------------------------------ header / provenance
    w("# RMC-Spark: measured results for the paper\n")
    w(f"_Generated {dt.datetime.now():%Y-%m-%d %H:%M} by `scripts/collect_results.py` from `{a.raw_dir}`. "
      "Every number below is computed from the raw files; re-run the script after more runs to refresh it._\n")
    w("> **How to use this file.** Section 3 gives, paragraph by paragraph, the value for every `[[placeholder]]` "
      "in `paper/content/06_results.txt`. Section 4 gives the hypothesis verdicts. Sections 7–9 are the full "
      "tables (copy into Tables 11/12). Section 10 lists the figures to insert. Section 11 lists caveats you must "
      "state in the paper.\n")

    w("## 1. Provenance and testbed\n")
    e = exp.get("experiment", {})
    started = exp.get("started")
    rows = [
        ["Experiment config", f"`{e.get('name', '?')}` ({a.raw_dir})"],
        ["Started", dt.datetime.fromtimestamp(started).strftime("%Y-%m-%d %H:%M") if started else "n/a"],
        ["Systems", ", ".join(S)],
        ["Workloads", ", ".join(sorted(runs["workload"].unique()))],
        ["Faults", ", ".join(sorted(runs["fault"].unique()))],
        ["Repetitions (configured)", e.get("repetitions", "n/a")],
        ["Runs recorded / analysed", f"{len(runs_all)} / {len(runs)} "
                                      f"({(runs_all['state'] == 'RUNNER_ERROR').sum()} runner errors excluded)"],
        ["Fault injected at (s after submit)", ", ".join(f"{k}: {v.get('fault_at_s')}" for k, v in
                                                         (e.get("workloads") or {}).items())],
        ["Transient fault duration (s)", e.get("transient_duration_s", "n/a")],
        ["Controller poll / probe timeout (s)", f"{ctl.get('poll_interval_s')} / {ctl.get('probe_timeout_s')}"],
        ["FAILED after (polls, H <)", f"{ctl.get('failed_consecutive')}, {ctl.get('failed_threshold')}"],
        ["Migrate after stall (s) / B3 timeout (s)", f"{ctl.get('migrate_stall_s')} / {ctl.get('naive_timeout_s')}"],
    ]
    env_path = "results/logs/environment.txt"
    if os.path.exists(env_path):
        with open(env_path, encoding="utf-8") as fh:
            for line in fh:
                if ":" in line:
                    k, v = line.split(":", 1)
                    rows.append([k.strip(), v.strip()])
    w(md_table(["Item", "Value"], rows))

    w("## 2. Verification evidence\n")
    for path in sorted(glob.glob("results/logs/pytest_*.txt")):
        with open(path, encoding="utf-8", errors="replace") as fh:
            tail = [ln.strip() for ln in fh if "passed" in ln or "failed" in ln]
        w(f"- `{path}`: **{tail[-1].strip('= ') if tail else 'no summary line'}**")
    for path in sorted(glob.glob("results/demo/*.txt")):
        w(f"- Live demo capture: `{path}`")
    w("")

    # ------------------------------------------------------------------ section 3: placeholders
    w("## 3. Values for the placeholders in `06_results.txt`\n")
    w("### 3.1 Fault Recovery Performance (paragraph 1)\n")
    rows = [[s, f(med(sub(faulty, system=s)["downtime_s"])), len(sub(faulty, system=s))] for s in S]
    w(md_table(["System", "Median downtime over all fault runs (s)", "n"], rows))
    co = sub(runs, fault="cluster_outage")
    if len(co):
        parts = []
        for s in S:
            g = sub(co, system=s)
            if not len(g):
                continue
            nfail = int((g["state"] != "SUCCEEDED").sum())
            parts.append(f"{SHORT.get(s, s)}: {len(g) - nfail}/{len(g)} succeeded, {nfail} failed "
                         f"({', '.join(sorted(set(g[g['state'] != 'SUCCEEDED']['outcome'].astype(str)))) or '-'}), "
                         f"median downtime {f(med(g['downtime_s']))} s, median failover {f(med(g['failover_s']))} s")
        w("**Cluster outages:** " + "; ".join(parts) + ".\n")
    det = [[s, f(med(sub(faulty, system=s, fault=FAILOVER_FAULTS + ['master_kill'])['detection_s'])),
            int(sub(faulty, system=s)["detection_s"].notna().sum())] for s in S]
    w("**Detection latency** (fault → FAILED transition by the system's own detector; health detector for "
      "P/A1/B1/B2, timeout detector for B3; computed over cluster_outage, network_partition, master_kill):\n")
    w(md_table(["System", "Median detection (s)", "runs with a detection"], det))
    if "P_rmc" in S and "B3_naive_ha" in S:
        c = compare(sub(faulty, system="P_rmc", fault=FAILOVER_FAULTS),
                    sub(faulty, system="B3_naive_ha", fault=FAILOVER_FAULTS), "P_rmc", "B3_naive_ha")
        w(f"**H2 test (downtime, failover faults, P vs B3):** {cmp_text(c)}.\n")

    w("### 3.2 Faults handled inside the cluster and gray failures (paragraph 2)\n")
    rows = []
    for fault in ["executor_kill", "worker_kill", "straggler", "network_delay"]:
        ref = sub(faulty, system="B1_vanilla", fault=fault)
        if not len(ref):
            continue
        for s in S:
            if s == "B1_vanilla":
                continue
            g = sub(faulty, system=s, fault=fault)
            if not len(g):
                continue
            c = compare(g, ref, s, "B1_vanilla", metric="delay_s")
            rows.append([fault, SHORT.get(s, s), f(c["med_a"]), f(c["med_b"]), f(c["delta"], 2), c["mag"],
                         pval(c["p"])])
    w(md_table(["Fault", "System", "Median delay (s)", "B1 median delay (s)", "Cliff's δ vs B1", "magnitude",
                "p"], rows) if rows else "_No executor_kill / worker_kill / straggler / network_delay runs yet._\n")

    w("### 3.3 Cluster Resilience and Workload Continuity (H1, H3, H4)\n")
    rows = []
    for s in S:
        r = [s]
        for fault in FAILOVER_FAULTS:
            g = sub(runs, system=s, fault=fault)
            r.append(f"{int(g['success'].sum())}/{len(g)} ({pct(g['success'].mean() if len(g) else None)})")
        rows.append(r)
    w("**Success rate under failover faults (H1):**\n")
    w(md_table(["System", "cluster_outage", "network_partition"], rows))

    mk = sub(runs, fault="master_kill")
    if len(mk):
        rows = []
        for s in S:
            g = sub(mk, system=s)
            ids = set(g["job_id"])
            keeps = sum(1 for d in decisions if d.get("kind") == "keep" and d.get("job_id") in ids)
            rows.append([s, len(g), int(g["success"].sum()), int((g["failovers"] > 0).sum()), keeps])
        w("**Master-only failures (H3):**\n")
        w(md_table(["System", "runs", "succeeded", "runs that migrated/restarted", "`keep` decisions logged"], rows))
    else:
        w("_No master_kill runs yet (H3 needs them)._\n")

    w3 = sub(runs, workload="iterative_rank")
    if len(w3):
        rows = [[s, f(mean(sub(w3, system=s, fault=list(set(w3['fault']) - {'none'}))["recomputed_s"])),
                 f(mean(sub(w3, system=s)["checkpoints"]), 1), f(mean(sub(w3, system=s)["checkpoint_s"]))]
                for s in S]
        w("**Long-lineage workload W3 (H4):**\n")
        w(md_table(["System", "Mean recomputed work under faults (s)", "Mean checkpoints per run",
                    "Mean checkpoint write time (s)"], rows))
    else:
        w("_No iterative_rank (W3) runs yet (H4 needs them)._\n")
    taus = [float(ev["tau_s"]) for jid, evs in events.items() if jid.startswith("P_rmc")
            for ev in evs if ev.get("event") == "stage_completed" and ev.get("tau_s") not in (None, float("inf"))
            and isinstance(ev.get("tau_s"), (int, float)) and math.isfinite(ev["tau_s"])]
    w(f"**τ\\* range observed by P (for the Fig. 14(b) sentence):** "
      f"{f(min(taus)) if taus else 'n/a'} s – {f(max(taus)) if taus else 'n/a'} s "
      f"(median {f(pd.Series(taus).median() if taus else None)} s, {len(taus)} stage decisions).\n")

    w("### 3.4 Throughput Stability for Streaming\n")
    st = sub(runs, workload="streaming")
    if len(st):
        rows = [[s, fault, len(g), f(med(g["stream_recovery_s"])), f(med(g["duration_s"]))]
                for (s, fault), g in st.groupby(["system", "fault"])]
        w(md_table(["System", "Fault", "runs", "Median streaming recovery (s)", "Median duration (s)"], rows))
    else:
        w("_No streaming runs yet._\n")

    w("### 3.5 Operational Availability\n")
    rows = []
    for s in S:
        m, lo, hi = bootstrap_ci(lst(sub(faulty, system=s)["availability"]))
        rows.append([s, f(m, 3), f"[{f(lo, 3)}, {f(hi, 3)}]", pct(sub(faulty, system=s)["success"].mean())])
    w(md_table(["System", "Mean run availability under faults", "95 % bootstrap CI", "Success rate"], rows))

    w("### 3.6 System Efficiency and Resource Utilisation\n")
    ts_path = os.path.join(a.raw_dir, "cluster_timeseries.csv")
    ex = sub(runs, system="P_rmc", fault="cluster_outage")
    ex = ex[ex["success"] == 1]
    if len(ex) and os.path.exists(ts_path):
        r = ex.iloc[0]
        ts = pd.read_csv(ts_path)
        wdw = ts[(ts["ts"] >= r["t_submit"]) & (ts["ts"] <= r["t_end"])].copy()
        wdw["u"] = wdw["cores_used"] / wdw["cores"].where(wdw["cores"] > 0)
        pre = wdw[wdw["ts"] < r["t_fault"]]
        post = wdw[wdw["ts"] >= r["t_fault"]]
        ua = pre[pre["cluster"] == "A"]["u"].mean()
        ub = pre[pre["cluster"] == "B"]["u"].fillna(0).mean()
        ha_min = post[post["cluster"] == "A"]["health"].min()
        rise = post[(post["cluster"] == "B") & (post["cores_used"] > 0)]["ts"]
        gap = (rise.iloc[0] - r["t_fault"]) if len(rise) else None
        w(f"Representative run `{r['job_id']}` (Fig. 23): before the fault cluster A utilisation = **{pct(ua)}**, "
          f"cluster B = **{pct(ub)}**; after the fault H_A fell to **{f(ha_min, 2)}**; the job was resubmitted "
          f"**{f(r['t_action'] - r['t_fault'])} s** after the fault and B's utilisation first rose "
          f"**{f(gap)} s** after the fault.\n")
    else:
        w("_No successful P_rmc cluster_outage run with a timeseries yet._\n")
    rows = [[s, pct(med(sub(clean, system=s)["overhead"])), f(med(sub(clean, system=s)["duration_s"])),
             len(sub(clean, system=s))] for s in S]
    w("**Fault-free overhead, Eq. (5) (H5):**\n")
    w(md_table(["System", "Overhead vs B1 (median)", "Median clean duration (s)", "clean runs"], rows))

    # ------------------------------------------------------------------ section 4: hypotheses
    w("## 4. Hypothesis verdicts\n")
    w("Verdict rule: *supported* if the direction matches and (with n ≥ 2 per group) p < 0.05 or |δ| is large; "
      "*not supported* if the direction is opposite or the effect is negligible; *inconclusive* when there are "
      "too few runs. Review each verdict yourself before writing it into the paper.\n")

    def verdict(direction_ok, c):
        if c is None or c["n_a"] == 0 or c["n_b"] == 0:
            return "inconclusive (no runs)"
        if not direction_ok:
            return "**not supported**"
        if c["p"] is not None and c["p"] < 0.05:
            return "**supported**"
        if c["delta"] == c["delta"] and abs(c["delta"]) >= 0.474:
            return "**supported (large effect; p not significant at this n)**" if c["p"] is not None \
                else "**direction supported, n too small for a test**"
        return "inconclusive (small effect / few runs)"

    rows = []
    # H1
    fo = sub(runs, fault=FAILOVER_FAULTS)
    if len(fo) and "P_rmc" in S:
        p_sr = sub(fo, system="P_rmc")["success"].mean()
        for base in ["B1_vanilla", "B2_fixed_ckpt"]:
            if base in S:
                c = compare(sub(fo, system="P_rmc").assign(x=lambda d: d["success"]),
                            sub(fo, system=base).assign(x=lambda d: d["success"]), "P_rmc", base, metric="x")
                b_sr = sub(fo, system=base)["success"].mean()
                rows.append(["H1 availability", f"P vs {SHORT[base]}", f"success {pct(p_sr)} vs {pct(b_sr)}; "
                             f"p = {pval(c['p'])}, δ = {f(c['delta'], 2)}", verdict(p_sr > b_sr, c)])
    # H2
    if "P_rmc" in S and "B3_naive_ha" in S:
        c = compare(sub(faulty, system="P_rmc", fault=FAILOVER_FAULTS),
                    sub(faulty, system="B3_naive_ha", fault=FAILOVER_FAULTS), "P_rmc", "B3_naive_ha")
        ok = c["med_a"] is not None and c["med_b"] is not None and c["med_a"] < c["med_b"]
        rows.append(["H2 recovery time", "P vs B3 downtime", cmp_text(c), verdict(ok, c)])
    # H3
    if len(mk) and "P_rmc" in S and "B3_naive_ha" in S:
        pm = int((sub(mk, system="P_rmc")["failovers"] > 0).sum())
        bm = int((sub(mk, system="B3_naive_ha")["failovers"] > 0).sum())
        n_p, n_b = len(sub(mk, system="P_rmc")), len(sub(mk, system="B3_naive_ha"))
        ok = pm == 0 and bm > 0
        rows.append(["H3 no unneeded restarts", "master_kill migrations", f"P {pm}/{n_p}, B3 {bm}/{n_b}",
                     "**supported**" if ok else ("**not supported**" if n_p and n_b else "inconclusive (no runs)")])
    # H4
    if len(w3):
        w3f = w3[w3["fault"] != "none"]
        p_rec = mean(sub(w3f, system=["P_rmc", "A1_rmc_no_adapt"])["recomputed_s"])
        b_rec = mean(sub(w3f, system=["B1_vanilla", "B2_fixed_ckpt", "B3_naive_ha"])["recomputed_s"])
        c = compare(sub(w3f, system=["P_rmc", "A1_rmc_no_adapt"]),
                    sub(w3f, system=["B1_vanilla", "B2_fixed_ckpt", "B3_naive_ha"]), "P+A1", "B1-B3",
                    metric="recomputed_s")
        ok = p_rec is not None and b_rec is not None and p_rec < b_rec
        rows.append(["H4 lost work (W3)", "P+A1 vs B1–B3 recomputed", f"mean {f(p_rec)} s vs {f(b_rec)} s; "
                     f"p = {pval(c['p'])}, δ = {f(c['delta'], 2)}", verdict(ok, c)])
    # H5
    if len(clean):
        ov = {s: med(sub(clean, system=s)["overhead"]) for s in S}
        others = [s for s in ("A1_rmc_no_adapt", "B2_fixed_ckpt") if ov.get(s) is not None]
        if ov.get("P_rmc") is not None and others:
            ok = all(ov["P_rmc"] < ov[s] for s in others)
            n_clean = min(len(sub(clean, system=s)) for s in ["P_rmc"] + others)
            rows.append(["H5 overhead", "P vs " + ", ".join(SHORT[s] for s in others),
                         "; ".join(f"{SHORT[s]} {pct(ov[s])}" for s in ["P_rmc"] + others),
                         ("**supported**" if ok else "**not supported**") +
                         (" (few clean runs, treat as indicative)" if n_clean < 3 else "")])
        else:
            rows.append(["H5 overhead", "P vs A1, B2", "needs clean runs of P, A1 and/or B2",
                         "inconclusive (no runs)"])
    w(md_table(["Hypothesis", "Comparison", "Evidence", "Verdict"], rows))

    # ------------------------------------------------------------------ ablation
    w("## 5. Ablation pairs (Comparative Analysis → Ablation Logic)\n")
    pairs = [("B2_fixed_ckpt", "B1_vanilla", "checkpointing without failover"),
             ("B3_naive_ha", "B1_vanilla", "naive failover without checkpoints"),
             ("A1_rmc_no_adapt", "B3_naive_ha", "health detection + progress-aware migration + resumption"),
             ("P_rmc", "A1_rmc_no_adapt", "adaptive checkpoint policy")]
    rows = []
    for x, y, what in pairs:
        if x in S and y in S:
            c = compare(sub(faulty, system=x), sub(faulty, system=y), x, y)
            ox, oy = med(sub(clean, system=x)["overhead"]), med(sub(clean, system=y)["overhead"])
            rows.append([f"{SHORT[x]} vs {SHORT[y]}", what, f"{f(c['med_a'])} vs {f(c['med_b'])}",
                         f"{f(c['delta'], 2)} ({c['mag']})", pval(c["p"]), f"{pct(ox)} vs {pct(oy)}"])
    w(md_table(["Pair", "Isolates", "Median downtime (s)", "Cliff's δ", "p", "Clean overhead"], rows)
      if rows else "_Needs the full matrix (B2, B3, A1)._\n")

    # ------------------------------------------------------------------ continuity
    w("## 6. Business continuity (Table: continuity matrix, Recovery Objectives)\n")
    starts = driver_startup(runs, events)
    w(f"**Median driver start-up time after a failover** (failover decision → new attempt's first event): "
      f"**{f(pd.Series(starts).median() if starts else None)} s** (n = {len(starts)}).\n")
    rows = [[s, f(sub(faulty, system=s)["downtime_s"].max()), f(mean(sub(faulty, system=s)["recomputed_s"]))]
            for s in S]
    w(md_table(["System", "Measured max downtime (s)", "Measured mean recomputed work (s)"], rows))
    rel = replay_reliability(ts_path, runs_all[runs_all["state"] != "RUNNER_ERROR"], ctl)
    if rel:
        w("**Reliability score R per cluster at the end of the experiment** (replayed from the timeseries, Eq. 10):\n")
        rows = []
        for c, sc in sorted(rel.items()):
            dom = max(sc["components"], key=lambda k: 1 - sc["components"][k])
            rows.append([c, f(sc["R"], 3)] + [f(sc["contributions"][k], 3) for k in
                                               ("availability", "recovery", "success", "health")] +
                        [sc["failures"], f(sc["mttr_s"]), f(sc["mtbf_s"], 0), f"lowest component: {dom}"])
        w(md_table(["Cluster", "R", "avail. contrib.", "recovery contrib.", "success contrib.", "health contrib.",
                    "failures", "MTTR (s)", "MTBF est. (s)", "note"], rows))

    # ------------------------------------------------------------------ tables
    w("## 7. Table 11 — Experimental Results Summary (from `analysis.report`)\n")
    for name in ["Table 11 Experimental Results Summary", "Table 12 Comparative Benchmark Analysis",
                 "Table S1 Streaming Recovery"]:
        pth = os.path.join(a.report, f"{name}.md")
        if os.path.exists(pth):
            if name.startswith("Table 12"):
                w("## 8. Table 12 — Comparative Benchmark Analysis (measured rows)\n")
            if name.startswith("Table S1"):
                w("## 9. Table S1 — Streaming Recovery\n")
            with open(pth, encoding="utf-8") as fh:
                w(fh.read().split("\n", 2)[-1])
        else:
            w(f"_`{pth}` not found — run `python -m analysis.report {a.raw_dir} --out {a.report}` first._\n")

    w("## 10. Figures to insert\n")
    figs = [("Fig 21 Fault Recovery Performance.png", "Fig. 21 (fig:recoveryperf)"),
            ("Fig 22 Availability and Success Rate.png", "Fig. 22 (fig:availability) — the paper calls it "
                                                         "'Availability and Uptime Evaluation'"),
            ("Fig 23 Resource Utilization and Cluster Stability.png", "Fig. 23 (fig:utilisation)"),
            ("Fig 24 Comparative Benchmark Radar.png", "Fig. 24 (fig:radar)")]
    rows = [[f"`{a.report}/{fn}`", where, "yes" if os.path.exists(os.path.join(a.report, fn)) else "**missing**"]
            for fn, where in figs]
    w(md_table(["File (600 DPI)", "Paper slot", "Exists"], rows))

    w("## 11. Caveats to state in the paper\n")
    reps = e.get("repetitions")
    n_cells = runs.groupby(["system", "workload", "fault"]).size()
    w(f"- Runs per (system, workload, fault) cell: min {n_cells.min() if len(n_cells) else 0}, "
      f"max {n_cells.max() if len(n_cells) else 0} (configured repetitions: {reps}). "
      "With fewer than 3 runs per cell, p-values are not meaningful; report effect sizes and medians and say so.")
    missing = [s for s in ORDER if s not in S]
    if missing:
        w(f"- Systems **not** in this dataset: {', '.join(missing)}. Rows for them in Tables 11/12 must stay "
          "empty or be removed; do not fill them from expectations.")
    w("- Single-host Docker testbed (all clusters on one laptop); network faults emulated with tc / docker network.")
    w("- P and A1 also enable `spark.speculation`; differences on straggler/network_delay may come from that.")
    w("- Thresholds in `configs/clusters.yaml` were set by reasoning, not tuned (no sensitivity analysis).")
    errs = runs_all[runs_all["state"] == "RUNNER_ERROR"]
    if len(errs):
        w(f"- {len(errs)} run(s) ended with RUNNER_ERROR and were excluded: "
          + "; ".join(f"{r.system}/{r.workload}/{r.fault}" for r in errs.itertuples()))
    w("")

    with open(a.out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L))
    print(f"wrote {a.out} ({len(runs)} runs)")


if __name__ == "__main__":
    main()
