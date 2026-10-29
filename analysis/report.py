"""Turn raw experiment output into the paper's result tables and figures (600 DPI).

    docker compose exec controller python -m analysis.report results/raw/full --out results/report

Outputs
  Table 11 Experimental Results Summary.{csv,md}
  Table 12 Comparative Benchmark Analysis.{csv,md}
  Table S1 Streaming Recovery.{csv,md}
  Fig 21 Fault Recovery Performance.png
  Fig 22 Availability and Success Rate.png
  Fig 23 Resource Utilization and Cluster Stability.png
  Fig 24 Comparative Benchmark Radar.png
Every number in these files comes from runs.csv / events / cluster_timeseries.csv.
"""
from __future__ import annotations

import argparse
import math
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from analysis.metrics import load_runs  # noqa: E402
from analysis.stats import bootstrap_ci, cliffs_delta, magnitude, mann_whitney  # noqa: E402

DPI = 600
SYSTEM_ORDER = ["B1_vanilla", "B2_fixed_ckpt", "B3_naive_ha", "A1_rmc_no_adapt", "P_rmc"]
COLORS = {"B1_vanilla": "#8c8c8c", "B2_fixed_ckpt": "#5b8db8", "B3_naive_ha": "#e3a23b",
          "A1_rmc_no_adapt": "#9d7bc4", "P_rmc": "#2e8b57"}
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8, "axes.spines.top": False,
                     "axes.spines.right": False})


def systems_in(df):
    present = list(dict.fromkeys(df["system"]))
    return [s for s in SYSTEM_ORDER if s in present] + [s for s in present if s not in SYSTEM_ORDER]


def to_markdown(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for _, r in df.iterrows():
        cells = []
        for c in cols:
            v = r[c]
            cells.append("" if v is None or (isinstance(v, float) and math.isnan(v))
                         else f"{v:.3g}" if isinstance(v, float) else str(v))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def save_table(df, out, name):
    df.to_csv(os.path.join(out, f"{name}.csv"), index=False)
    with open(os.path.join(out, f"{name}.md"), "w", encoding="utf-8") as fh:
        fh.write(f"### {name}\n\n" + to_markdown(df))


def table11(runs):
    rows = []
    for (s, f), g in runs.groupby(["system", "fault"]):
        rows.append({"system": s, "fault": f, "runs": len(g), "success_rate": g["success"].mean(),
                     "median_duration_s": g["duration_s"].median(),
                     "median_downtime_s": g["downtime_s"].median(),
                     "median_detection_s": g["detection_s"].median(),
                     "median_failover_s": g["failover_s"].median(),
                     "mean_recomputed_s": g["recomputed_s"].mean(),
                     "mean_checkpoint_s": g["checkpoint_s"].mean(),
                     "mean_availability": g["availability"].mean()})
    df = pd.DataFrame(rows)
    df["system"] = pd.Categorical(df["system"], systems_in(runs), ordered=True)
    return df.sort_values(["fault", "system"]).reset_index(drop=True)


def table12(runs, reference="B1_vanilla"):
    faulty = runs[runs["fault"] != "none"]
    clean = runs[runs["fault"] == "none"]
    ref_down = faulty[faulty["system"] == reference]["downtime_s"].tolist()
    rows = []
    for s in systems_in(runs):
        f = faulty[faulty["system"] == s]
        c = clean[clean["system"] == s]
        mean_av, lo, hi = bootstrap_ci(f["availability"].tolist())
        d = cliffs_delta(f["downtime_s"].tolist(), ref_down) if s != reference else float("nan")
        rows.append({
            "system": s, "fault_runs": len(f), "success_rate": f["success"].mean() if len(f) else None,
            "availability_mean": mean_av, "availability_ci_low": lo, "availability_ci_high": hi,
            "median_downtime_s": f["downtime_s"].median(), "mean_recomputed_s": f["recomputed_s"].mean(),
            "clean_overhead_vs_B1": c["overhead"].median() if len(c) else None,
            "p_downtime_vs_B1": mann_whitney(f["downtime_s"].tolist(), ref_down) if s != reference else None,
            "cliffs_delta_vs_B1": d, "effect": magnitude(d) if d == d else "",
        })
    return pd.DataFrame(rows)


def fig21(runs, out):
    faulty = runs[runs["fault"] != "none"]
    faults = sorted(faulty["fault"].unique())
    systems = systems_in(runs)
    fig, ax = plt.subplots(figsize=(7.2, 3.2))
    width = 0.8 / max(1, len(systems))
    for i, s in enumerate(systems):
        data = [faulty[(faulty["fault"] == f) & (faulty["system"] == s)]["downtime_s"].dropna().tolist()
                for f in faults]
        pos = [j + (i - (len(systems) - 1) / 2) * width for j in range(len(faults))]
        bp = ax.boxplot([d if d else [float("nan")] for d in data], positions=pos, widths=width * 0.9,
                        patch_artist=True, showfliers=True, flierprops={"markersize": 2})
        for b in bp["boxes"]:
            b.set_facecolor(COLORS.get(s, "#cccccc"))
            b.set_linewidth(0.6)
        ax.plot([], [], color=COLORS.get(s, "#cccccc"), lw=6, label=s)
    ax.set_xticks(range(len(faults)))
    ax.set_xticklabels([f.replace("_", "\n") for f in faults])
    ax.set_ylabel("Downtime per fault (s)")
    ax.set_title("Fault recovery performance (lower is better)")
    ax.legend(ncol=len(systems), fontsize=6, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.22))
    fig.tight_layout()
    fig.savefig(os.path.join(out, "Fig 21 Fault Recovery Performance.png"), dpi=DPI)
    plt.close(fig)


def fig22(runs, out):
    faulty = runs[runs["fault"] != "none"]
    systems = systems_in(runs)
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(7.2, 2.8))
    for i, s in enumerate(systems):
        g = faulty[faulty["system"] == s]
        m, lo, hi = bootstrap_ci(g["availability"].tolist())
        if m is not None:
            a1.bar(i, m, color=COLORS.get(s), yerr=[[m - lo], [hi - m]], capsize=3)
        a2.bar(i, g["success"].mean() if len(g) else 0, color=COLORS.get(s))
    for ax, title in ((a1, "Run availability under faults (mean, 95% CI)"), (a2, "Job success rate under faults")):
        ax.set_xticks(range(len(systems)))
        ax.set_xticklabels(systems, rotation=25, ha="right", fontsize=6)
        ax.set_ylim(0, 1.05)
        ax.set_title(title, fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(out, "Fig 22 Availability and Success Rate.png"), dpi=DPI)
    plt.close(fig)


def fig23(runs, raw_dir, out):
    ts = pd.read_csv(os.path.join(raw_dir, "cluster_timeseries.csv"))
    ex = runs[(runs["system"] == "P_rmc") & (runs["fault"] == "cluster_outage") & (runs["success"] == 1)]
    if ex.empty:
        ex = runs[runs["fault"] != "none"]
    if ex.empty:
        return
    r = ex.iloc[0]
    w = ts[(ts["ts"] >= r["t_submit"] - 10) & (ts["ts"] <= r["t_end"] + 10)].copy()
    w["t"] = w["ts"] - r["t_submit"]
    w["util"] = w["cores_used"] / w["cores"].where(w["cores"] > 0)
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(7.2, 4), sharex=True)
    for c, g in w.groupby("cluster"):
        a1.plot(g["t"], g["util"].fillna(0), label=f"cluster {c}", lw=1)
        a2.plot(g["t"], g["health"], label=f"cluster {c}", lw=1)
    for ax in (a1, a2):
        if r["t_fault"] == r["t_fault"]:
            ax.axvline(r["t_fault"] - r["t_submit"], color="red", ls="--", lw=0.8)
        if r["t_action"] == r["t_action"]:
            ax.axvline(r["t_action"] - r["t_submit"], color="green", ls=":", lw=0.8)
        ax.legend(fontsize=6, frameon=False)
    a1.set_ylabel("Core utilisation U")
    a2.set_ylabel("Health H_k")
    a2.set_xlabel("Time since submission (s)   red: fault injected, green: job resubmitted")
    a1.set_title(f"{r['system']} / {r['workload']} / {r['fault']}")
    fig.tight_layout()
    fig.savefig(os.path.join(out, "Fig 23 Resource Utilization and Cluster Stability.png"), dpi=DPI)
    plt.close(fig)


def fig24(t12, out):
    axes_def = [("success_rate", False), ("availability_mean", False), ("median_downtime_s", True),
                ("mean_recomputed_s", True), ("clean_overhead_vs_B1", True)]
    labels = ["Success", "Availability", "Low downtime", "Low recompute", "Low overhead"]
    df = t12.copy()
    for col, invert in axes_def:
        v = df[col].astype(float)
        lo, hi = v.min(), v.max()
        norm = (v - lo) / (hi - lo) if hi > lo else v * 0 + 1.0
        df[col + "_n"] = 1 - norm if invert else norm
    n = len(axes_def)
    angles = [i / n * 2 * math.pi for i in range(n)] + [0]
    fig = plt.figure(figsize=(4.2, 4.2))
    ax = fig.add_subplot(111, polar=True)
    for _, r in df.iterrows():
        vals = [float(r[c + "_n"]) if r[c + "_n"] == r[c + "_n"] else 0.0 for c, _ in axes_def]
        vals += vals[:1]
        ax.plot(angles, vals, color=COLORS.get(r["system"]), lw=1.2, label=r["system"])
        ax.fill(angles, vals, color=COLORS.get(r["system"]), alpha=0.08)
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(labels, fontsize=7)
    ax.set_yticklabels([])
    ax.legend(fontsize=6, frameon=False, loc="upper right", bbox_to_anchor=(1.35, 1.1))
    ax.set_title("Comparative benchmark (min-max normalised, outer = better)", fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(out, "Fig 24 Comparative Benchmark Radar.png"), dpi=DPI)
    plt.close(fig)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("raw_dir")
    p.add_argument("--out", default="results/report")
    a = p.parse_args()
    os.makedirs(a.out, exist_ok=True)
    runs = load_runs(a.raw_dir)
    # a fault run whose job finished before fault_at_s never saw the fault; counting it would credit
    # the system with surviving a fault it never experienced
    missed = (runs["fault"] != "none") & runs["t_fault"].isna()
    if missed.any():
        print(f"excluding {int(missed.sum())} fault runs where the fault was never injected:")
        print(runs.loc[missed, ["rep", "system", "fault", "duration_s"]].to_string(index=False))
        runs = runs[~missed]
    runs.to_csv(os.path.join(a.out, "runs_enriched.csv"), index=False)
    t11, t12 = table11(runs), table12(runs)
    save_table(t11, a.out, "Table 11 Experimental Results Summary")
    save_table(t12, a.out, "Table 12 Comparative Benchmark Analysis")
    st = runs[runs["workload"] == "streaming"].groupby(["system", "fault"])["stream_recovery_s"] \
        .agg(["count", "median"]).reset_index()
    if not st.empty:
        save_table(st, a.out, "Table S1 Streaming Recovery")
    fig21(runs, a.out)
    fig22(runs, a.out)
    fig23(runs, a.raw_dir, a.out)
    if len(t12) > 1:
        fig24(t12, a.out)
    print(to_markdown(t12))
    print(f"report written to {a.out}")


if __name__ == "__main__":
    main()
