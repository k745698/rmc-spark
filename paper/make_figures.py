"""Draw all manuscript figures at 600 DPI into paper/Diagrams/ ("Fig NN <Title>.png").

Conceptual diagrams are drawn programmatically (so they are reproducible and editable);
Fig 13(b) is computed from Eqs. (4)-(5); Figs 21-24 and 28 are placeholders until the
experiments are run (analysis/report.py produces the real ones).
Run with:  python paper/make_figures.py      (needs matplotlib + numpy)
"""
from __future__ import annotations

import math
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Diagrams")
DPI = 600
COL_W, WIDE_W = 3.45, 7.0

BLUE, LBLUE = "#00629B", "#E3F0F8"
GREEN, LGREEN = "#2E7D4F", "#E6F4EC"
ORANGE, LORANGE = "#C77C12", "#FDF1DC"
RED, LRED = "#B03A2E", "#FBE5E3"
PURPLE, LPURPLE = "#6A4C93", "#EFE9F7"
GREY, LGREY = "#555555", "#F2F2F2"
INK = "#1A1A1A"

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 6})


# ----------------------------------------------------------------------------- helpers
def canvas(width_in, height_in, W=100.0):
    H = W * height_in / width_in
    fig = plt.figure(figsize=(width_in, height_in))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, W)
    ax.set_ylim(0, H)
    ax.axis("off")
    return fig, ax, H


def box(ax, x, y, w, h, text="", fc=LBLUE, ec=BLUE, fs=6, bold=False, tc=INK, lw=0.7, ls="-",
        pad=0.6, align="center", va="center", rounding=1.2, alpha=1.0, zorder=2):
    p = FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0,rounding_size={rounding}",
                       fc=fc, ec=ec, lw=lw, ls=ls, alpha=alpha, zorder=zorder)
    ax.add_patch(p)
    if text:
        if align == "center":
            tx = x + w / 2
        elif align == "left":
            tx = x + pad
        else:
            tx = x + w - pad
        ty = y + h / 2 if va == "center" else (y + h - pad if va == "top" else y + pad)
        ax.text(tx, ty, text, ha=align, va=va, fontsize=fs, color=tc,
                fontweight="bold" if bold else "normal", zorder=zorder + 1, linespacing=1.15)
    return (x, y, w, h)


def group(ax, x, y, w, h, title, fc=LGREY, ec=GREY, fs=6, tc=GREY, ls="-"):
    box(ax, x, y, w, h, fc=fc, ec=ec, lw=0.6, ls=ls, zorder=1)
    ax.text(x + 0.8, y + h - 0.8, title, ha="left", va="top", fontsize=fs, color=tc, fontweight="bold",
            zorder=3)


def arrow(ax, p1, p2, text=None, color=GREY, lw=0.7, ls="-", fs=5, rad=0.0, both=False, toff=(0, 0.9),
          tcolor=None, zorder=4):
    style = "<|-|>" if both else "-|>"
    a = FancyArrowPatch(p1, p2, arrowstyle=style, mutation_scale=5, color=color, lw=lw, ls=ls,
                        connectionstyle=f"arc3,rad={rad}", zorder=zorder, shrinkA=0, shrinkB=0)
    ax.add_patch(a)
    if text:
        mx, my = (p1[0] + p2[0]) / 2 + toff[0], (p1[1] + p2[1]) / 2 + toff[1]
        ax.text(mx, my, text, ha="center", va="center", fontsize=fs, color=tcolor or color, zorder=zorder + 1,
                bbox=dict(fc="white", ec="none", pad=0.3, alpha=0.85))


def mid(b, side):
    x, y, w, h = b
    return {"l": (x, y + h / 2), "r": (x + w, y + h / 2), "t": (x + w / 2, y + h), "b": (x + w / 2, y)}[side]


def title(ax, x, y, text, fs=7, color=BLUE):
    ax.text(x, y, text, ha="left", va="top", fontsize=fs, color=color, fontweight="bold")


def save(fig, name):
    os.makedirs(OUT, exist_ok=True)
    fig.savefig(os.path.join(OUT, f"{name}.png"), dpi=DPI, bbox_inches="tight", pad_inches=0.03)
    plt.close(fig)


# ----------------------------------------------------------------------------- figures
def fig01():
    fig, ax, H = canvas(COL_W, 2.3)
    ax.annotate("", xy=(98, 20), xytext=(2, 20), arrowprops=dict(arrowstyle="-|>", color=BLUE, lw=1.2))
    items = [(10, "2004", "MapReduce", "task\nre-execution"), (26, "2012-13", "RDDs, YARN", "lineage\nrecomputation"),
             (42, "2015", "Flink, Spark SQL", "distributed\nsnapshots"), (58, "2015-16", "Borg, Kubernetes", "orchestrated\nrestarts"),
             (74, "2018", "Structured\nStreaming", "exactly-once\ncheckpoints"), (89, "2020+", "cloud-native,\nmulti-cluster", "cross-cluster\nresilience")]
    for i, (x, yr, name, ft) in enumerate(items):
        ax.plot([x], [20], "o", color=BLUE, ms=3)
        up = i % 2 == 0
        y0 = 24 if up else 6
        box(ax, x - 7.5, y0, 15, 10, f"{name}", fc=LBLUE if i < 5 else LGREEN, ec=BLUE if i < 5 else GREEN, fs=5.2, bold=True)
        ax.text(x, 20 + (2.0 if not up else -2.4), yr, ha="center", va="center", fontsize=5, color=GREY)
        ax.text(x, y0 + (13.2 if up else -2.8), ft, ha="center", va="center", fontsize=4.8, color=GREY, style="italic")
    ax.text(50, H - 1.5, "Scope of fault tolerance widens with each generation", ha="center", va="top", fontsize=6,
            color=BLUE, fontweight="bold")
    save(fig, "Fig 01 Evolution of Distributed Analytics Platforms")


def fig02():
    fig, ax, H = canvas(COL_W, 2.6)
    people = [("Data engineers", 4), ("Data scientists", 36), ("Platform engineers", 68)]
    for t, x in people:
        box(ax, x, H - 9, 28, 6, t, fc=LORANGE, ec=ORANGE, fs=5.5, bold=True)
    layers = [("Analytics programs: pipelines, features, models (rds stages)", LGREEN, GREEN),
              ("Platform services: Spark clusters, controller, monitoring", LBLUE, BLUE),
              ("Shared storage: object store, data lake, checkpoints", LPURPLE, PURPLE)]
    y = H - 20
    for t, fc, ec in layers:
        box(ax, 4, y, 70, 8, t, fc=fc, ec=ec, fs=5.3)
        y -= 11
    for x in (18, 50, 82):
        arrow(ax, (x, H - 9), (min(x, 60), H - 12), color=ORANGE)
    group(ax, 77, 8, 20, H - 20, "Failure\nsources", fc=LRED, ec=RED, tc=RED, fs=5)
    for i, t in enumerate(["code bugs", "executor OOM", "node loss", "network", "storage", "cluster outage"]):
        ax.text(87, H - 22 - i * 5, t, ha="center", va="center", fontsize=4.8, color=RED)
    ax.text(39, 3, "Resilience must span programs, platform and storage", ha="center", fontsize=5.5, color=BLUE,
            fontweight="bold")
    save(fig, "Fig 02 Resilient Data Science Ecosystem")


def fig03():
    fig, ax, H = canvas(COL_W, 2.4)
    rows = [("Task", "executor crash, OOM, bad record", "Spark task retry", LGREEN, GREEN, 40),
            ("Node", "worker host or disk lost", "Spark reschedules, recomputes", LBLUE, BLUE, 55),
            ("Gray", "network delay, straggler, slow disk", "often nobody (speculation)", LORANGE, ORANGE, 70),
            ("Cluster", "master, network partition, zone loss", "nobody: job lost (B1)\nRMC-Spark controller", LRED, RED, 92)]
    y = H - 6
    ax.text(3, H - 1.5, "Scope", fontsize=5.5, fontweight="bold", color=GREY, va="top")
    ax.text(16, H - 1.5, "Example", fontsize=5.5, fontweight="bold", color=GREY, va="top")
    ax.text(60, H - 1.5, "First responder", fontsize=5.5, fontweight="bold", color=GREY, va="top")
    for name, ex, resp, fc, ec, w in rows:
        y -= 10.5
        box(ax, 2, y, w * 0.98, 9, "", fc=fc, ec=ec)
        ax.text(4, y + 4.5, name, fontsize=6, fontweight="bold", va="center", color=ec)
        ax.text(16, y + 4.5, ex, fontsize=5, va="center")
        ax.text(60, y + 4.5, resp, fontsize=5, va="center", color=ec)
    ax.annotate("", xy=(97, 3), xytext=(97, H - 8), arrowprops=dict(arrowstyle="-|>", color=GREY, lw=0.8))
    ax.text(95.5, H / 2 - 4, "blast radius", rotation=90, fontsize=5, color=GREY, ha="center", va="center")
    save(fig, "Fig 03 Failure Scenarios in Distributed Analytics")


def fig04():
    fig, ax, H = canvas(WIDE_W, 4.0)
    root = box(ax, 38, H - 9, 24, 6, "Resilient distributed analytics", fc=BLUE, ec=BLUE, tc="white", bold=True, fs=7)
    branches = [("Engine-level\nrecovery", ["RDD lineage", "recomputation (RCMP)", "lineage checkpoint", "write-ahead lineage"]),
                ("Checkpoint\noptimisation", ["Young / Daly interval", "online MTBF (En-CHORE)", "stream-optimal interval", "failure-aware (FATM)"]),
                ("Stragglers &\ngray failures", ["LATE, Mantri", "RL identification", "tuple scheduling", "gray failure model"]),
                ("Prediction &\nAIOps", ["task / node failure", "disk failure", "anomaly detection", "root cause analysis"]),
                ("Multi-cluster\norchestration", ["Borg / Kubernetes", "multi-cloud scheduling", "geo-distributed analytics", "RL multi-cloud Spark"]),
                ("Resilience\nengineering", ["chaos engineering", "reliability models", "recovery benchmarks", "SLO / SLA"])]
    n = len(branches)
    for i, (b, leaves) in enumerate(branches):
        x = 2 + i * (96 / n)
        bb = box(ax, x, H - 22, 96 / n - 2, 8, b, fc=LBLUE, ec=BLUE, bold=True, fs=6)
        arrow(ax, mid(root, "b"), mid(bb, "t"), color=BLUE)
        for j, leaf in enumerate(leaves):
            box(ax, x + 1, H - 31 - j * 6.2, 96 / n - 4, 5, leaf, fc="white", ec=GREY, fs=5.2)
    box(ax, 30, 1.2, 40, 4.5, "RMC-Spark combines elements of all six branches", fc=LGREEN, ec=GREEN, fs=6, bold=True)
    save(fig, "Fig 04 Literature Taxonomy Framework")


def fig05():
    fig, ax, H = canvas(COL_W, 2.6)
    cols = [("Stakeholders", ["data scientists", "data engineers", "platform team", "business owner"], LORANGE, ORANGE),
            ("Requirements", ["F1-F7 functional", "N1 availability", "N2 overhead", "N3-N5 quality"], LBLUE, BLUE),
            ("Components", ["C1 monitor", "C2 checkpoints", "C3 failover", "C4/C5 placement,\nexplanation"], LGREEN, GREEN),
            ("Verification", ["unit tests (56)", "simulation", "fault experiments", "design review"], LPURPLE, PURPLE)]
    w = 22
    for i, (t, items, fc, ec) in enumerate(cols):
        x = 2 + i * 25
        ax.text(x + w / 2, H - 2, t, ha="center", va="top", fontsize=6, fontweight="bold", color=ec)
        for j, it in enumerate(items):
            box(ax, x, H - 13 - j * 10, w, 8, it, fc=fc, ec=ec, fs=5)
        if i < 3:
            arrow(ax, (x + w, H / 2 - 2), (x + 25, H / 2 - 2), color=GREY)
    ax.text(50, 2, "traceability: concern → requirement → component → evidence", ha="center", fontsize=5.3, color=GREY,
            style="italic")
    save(fig, "Fig 05 Requirements Engineering Framework")


def fig06():
    fig, ax, H = canvas(WIDE_W, 3.6)
    # controller
    group(ax, 2, H - 34, 34, 31, "Controller container", fc=LGREEN, ec=GREEN, tc=GREEN, fs=6.5)
    api = box(ax, 4, H - 12, 30, 5, "REST API · Prometheus exporter · CLI", fc="white", ec=GREEN, fs=5.5)
    loop = box(ax, 4, H - 23, 30, 9, "Control loop (2 s)\nC1 health · C3 failover · C4 placement\nC5 decision log · MTBF estimate",
               fc="white", ec=GREEN, fs=5.5)
    drv = box(ax, 4, H - 32, 30, 7, "Spark drivers (client mode)\nattempt n of each job + rds library (C2)", fc="white",
              ec=GREEN, fs=5.5)
    arrow(ax, mid(loop, "b"), mid(drv, "t"), color=GREEN, text="start / stop")

    def cluster(x, name):
        group(ax, x, H - 34, 26, 31, f"Spark cluster {name}", fc=LBLUE, ec=BLUE, tc=BLUE, fs=6.5)
        m = box(ax, x + 4, H - 13, 18, 5, f"master {name}", fc="white", ec=BLUE, fs=5.5, bold=True)
        w1 = box(ax, x + 2, H - 27, 10.5, 9, f"worker\n{name.lower()}1\n2 executors", fc="white", ec=BLUE, fs=5)
        w2 = box(ax, x + 13.5, H - 27, 10.5, 9, f"worker\n{name.lower()}2\n2 executors", fc="white", ec=BLUE, fs=5)
        arrow(ax, mid(m, "b"), mid(w1, "t"), color=BLUE)
        arrow(ax, mid(m, "b"), mid(w2, "t"), color=BLUE)
        return m, w1, w2
    ma, wa1, wa2 = cluster(42, "A")
    mb, wb1, wb2 = cluster(72, "B")
    store = box(ax, 42, 3, 56, 8, "Shared object storage (MinIO / S3)\ndata · checkpoints + commit markers · results",
                fc=LPURPLE, ec=PURPLE, fs=6, bold=True)
    for w in (wa1, wa2, wb1, wb2):
        arrow(ax, mid(w, "b"), (mid(w, "b")[0], 11), color=PURPLE, both=True)
    arrow(ax, (34, H - 8), (46, H - 10.5), text="probe /json", color=GREEN, fs=5)
    arrow(ax, (34, H - 28), (44, H - 22), text="executors", color=BLUE, fs=5)
    arrow(ax, (34, H - 29.5), (74, H - 22), color=BLUE, ls="--", rad=-0.15)
    ax.text(62, H - 37.5, "failover: next attempt on B", fontsize=5, color=BLUE, ha="center", style="italic")
    prom = box(ax, 4, 3, 15, 8, "Prometheus", fc=LORANGE, ec=ORANGE, fs=5.5, bold=True)
    graf = box(ax, 21, 3, 15, 8, "Grafana", fc=LORANGE, ec=ORANGE, fs=5.5, bold=True)
    arrow(ax, mid(prom, "r"), mid(graf, "l"), color=ORANGE)
    arrow(ax, (12, 11), (12, H - 34), color=ORANGE, text="scrape", fs=5)
    fi = box(ax, 81, 13.5, 17, 6, "Fault injector\n(Docker API)", fc=LRED, ec=RED, fs=5.2)
    arrow(ax, (85, 19.5), (55, H - 34), color=RED, ls="--", text="kill · pause · tc · disconnect", fs=4.8, rad=0.1)
    save(fig, "Fig 06 Resilient Multi-Cluster Spark Architecture")


def fig07():
    fig, ax, H = canvas(COL_W, 2.6)
    layers = [("Governance: access, audit, policies (XII)", LGREY, GREY),
              ("Explainability: decision log, reliability score R (XI)", LPURPLE, PURPLE),
              ("Control: monitor, detect, recover, place (VIII-X)", LGREEN, GREEN),
              ("Resilience programming: rds stages, checkpoints (IX)", LORANGE, ORANGE),
              ("Processing: Spark clusters A and B (VII)", LBLUE, BLUE),
              ("Storage: shared object store (VI)", "#E9E4F5", PURPLE)]
    y = H - 9
    for t, fc, ec in layers:
        box(ax, 2, y, 80, 7, t, fc=fc, ec=ec, fs=5.4)
        y -= 8.3
    box(ax, 84, y + 8.3, 14, H - 9 - y, "Observability\n(Prometheus,\nGrafana,\nevents)", fc="white", ec=ORANGE, fs=5)
    save(fig, "Fig 07 Layered Analytics Stack")


def fig08():
    fig, ax, H = canvas(WIDE_W, 2.4)
    srcs = ["Synthetic generator\n(seeded)", "NYC TLC trips", "AI4I 2020", "ULB credit card"]
    for i, s in enumerate(srcs):
        box(ax, 1, H - 8 - i * 7.5, 15, 6, s, fc=LORANGE, ec=ORANGE, fs=5.2)
        arrow(ax, (16, H - 5 - i * 7.5), (21, H / 2 + 2), color=ORANGE)
    data = box(ax, 21, H / 2 - 4, 12, 12, "data\nbucket", fc=LPURPLE, ec=PURPLE, fs=6, bold=True)
    stages = ["clean", "enrich", "hourly_agg", "zone_rank"]
    prev = data
    for i, s in enumerate(stages):
        b = box(ax, 38 + i * 13, H / 2 - 3, 11, 10, f"stage\n{s}", fc=LGREEN, ec=GREEN, fs=5.5, bold=True)
        arrow(ax, mid(prev, "r") if i < 3 else (38 + 1 * 13 + 11, H / 2 + 2), mid(b, "l"), color=GREEN)
        arrow(ax, mid(b, "b"), (mid(b, "b")[0], 7), color=PURPLE, ls="--")
        prev = b
    ck = box(ax, 38, 1, 50, 6, "checkpoint bucket: <job>/<stage>/data + _RDS_COMMIT marker (written last)",
             fc=LPURPLE, ec=PURPLE, fs=5.3)
    res = box(ax, 91, H / 2 - 4, 8, 12, "results\nbucket", fc=LPURPLE, ec=PURPLE, fs=5.5, bold=True)
    arrow(ax, (38 + 3 * 13 + 11, H / 2 + 2), mid(res, "l"), color=GREEN)
    ax.text(63, H - 2, "restore if committed  →  else compute, materialise, policy decides checkpoint", ha="center",
            va="top", fontsize=5.5, color=GREEN, style="italic")
    save(fig, "Fig 08 Distributed Data Engineering Pipeline")


def fig09():
    fig, ax, H = canvas(COL_W, 1.6)
    group(ax, 2, H - 26, 40, 23, "Controller container", fc=LGREEN, ec=GREEN, tc=GREEN)
    d = box(ax, 4, H - 24, 36, 15, "Driver\nSparkSession · Catalyst\nDAG scheduler\ntask scheduler", fc="white", ec=GREEN, fs=5.3)
    group(ax, 48, H - 26, 50, 23, "Cluster (standalone)", fc=LBLUE, ec=BLUE, tc=BLUE)
    m = box(ax, 55, H - 13, 36, 6, "master: resource allocation", fc="white", ec=BLUE, fs=5.3)
    w = box(ax, 50, H - 24, 22, 9, "worker\nexecutor · tasks\ncache", fc="white", ec=BLUE, fs=5)
    w2 = box(ax, 74, H - 24, 22, 9, "worker\nexecutor · tasks\ncache", fc="white", ec=BLUE, fs=5)
    arrow(ax, (40, H - 10), mid(m, "l"), text="register", color=GREY, fs=4.8)
    arrow(ax, (40, H - 20), mid(w, "l"), text="tasks", color=GREY, fs=4.8, both=True)
    s = box(ax, 2, 2, 96, 7, "Shared object storage (S3A)", fc=LPURPLE, ec=PURPLE, fs=5.5, bold=True)
    for b in (w, w2):
        arrow(ax, mid(b, "b"), (mid(b, "b")[0], 9), color=PURPLE, both=True)
    arrow(ax, mid(d, "b"), (22, 9), color=PURPLE, both=True, ls="--")
    save(fig, "Fig 09 Spark Execution Architecture")


def fig10():
    fig, ax, H = canvas(WIDE_W, 2.2)
    rs = [("clean", ["read parquet", "filter / withColumn"], "narrow"),
          ("enrich", ["broadcast join ×2"], "narrow"),
          ("hourly_agg", ["groupBy (shuffle)", "agg, percentile"], "wide"),
          ("zone_rank", ["groupBy (shuffle)", "window rank"], "wide")]
    x = 2
    for i, (name, ops, kind) in enumerate(rs):
        group(ax, x, 5, 22, H - 8, f"resilient stage: {name}", fc=LGREEN, ec=GREEN, tc=GREEN, fs=5.5)
        for j, op in enumerate(ops):
            box(ax, x + 2, H - 13 - j * 8, 18, 6, op, fc="white", ec=BLUE if kind == "narrow" else ORANGE, fs=5.2)
        ax.text(x + 11, 7.5, f"{kind} deps", ha="center", fontsize=4.8, color=GREY, style="italic")
        if i < 3:
            ax.plot([x + 23.2, x + 23.2], [3, H - 2], color=RED, lw=0.8, ls="--")
            ax.text(x + 23.6, 2.2, "commit = lineage cut\n(if policy checkpoints)", fontsize=4.8, color=RED, va="bottom")
            arrow(ax, (x + 22, H / 2), (x + 25, H / 2), color=GREEN)
        x += 25
    save(fig, "Fig 10 DAG Processing Workflow")


def fig11():
    fig, ax, H = canvas(COL_W, 1.6)
    sp = box(ax, 2, H - 12, 30, 9, "Spark masters\n& workers\n(metrics servlet)", fc=LBLUE, ec=BLUE, fs=5.2)
    dr = box(ax, 2, H - 25, 30, 9, "Spark drivers\n(REST API:\nexecutors, tasks)", fc=LBLUE, ec=BLUE, fs=5.2)
    ctl = box(ax, 40, H - 25, 26, 22, "Controller\nprobes → signals\n→ health H\n→ state machine\n→ decisions", fc=LGREEN,
              ec=GREEN, fs=5.2)
    pr = box(ax, 74, H - 12, 24, 9, "Prometheus\n(5 s scrape)", fc=LORANGE, ec=ORANGE, fs=5.2)
    gr = box(ax, 74, H - 25, 24, 9, "Grafana\ndashboard", fc=LORANGE, ec=ORANGE, fs=5.2)
    arrow(ax, mid(sp, "r"), (40, H - 7.5), text="/json probe (2 s)", color=GREEN, fs=4.6)
    arrow(ax, mid(dr, "r"), (40, H - 20.5), text="progress", color=GREEN, fs=4.6)
    arrow(ax, (32, H - 5), (74, H - 5), color=ORANGE, rad=-0.15)
    arrow(ax, (66, H - 14), mid(pr, "l"), text="/metrics", color=ORANGE, fs=4.6)
    arrow(ax, mid(pr, "b"), mid(gr, "t"), color=ORANGE)
    box(ax, 2, 2, 96, 7, "decision path (direct, 2 s)   vs   operator path (Prometheus/Grafana, 5 s)", fc="white", ec=GREY,
        fs=5.2)
    save(fig, "Fig 11 Monitoring and Observability Architecture")


def fig12():
    fig, ax, H = canvas(COL_W, 1.6)
    steps = ["poll every 2 s", "probe master + driver", "5 signals → a_i", "H = 1 − Σ w_i a_i", "update state machine"]
    for i, s in enumerate(steps):
        b = box(ax, 2, H - 8 - i * 8.5, 30, 6, s, fc=LBLUE, ec=BLUE, fs=5.2)
        if i < len(steps) - 1:
            arrow(ax, mid(b, "b"), (17, H - 8 - (i + 1) * 8.5 + 6), color=BLUE)
    hs = box(ax, 50, H - 10, 22, 7, "HEALTHY", fc=LGREEN, ec=GREEN, fs=6, bold=True)
    su = box(ax, 76, H - 26, 22, 7, "SUSPECT", fc=LORANGE, ec=ORANGE, fs=6, bold=True)
    fa = box(ax, 50, H - 42, 22, 7, "FAILED", fc=LRED, ec=RED, fs=6, bold=True)
    arrow(ax, (72, H - 7), (87, H - 19), text="H < 0.95", color=ORANGE, fs=4.6, rad=-0.3)
    arrow(ax, (80, H - 19), (68, H - 10), text="H ≥ 0.95", color=GREEN, fs=4.6, rad=-0.2, toff=(-4, -1))
    arrow(ax, (82, H - 26), (70, H - 35), text="3 polls\nH < 0.50", color=RED, fs=4.6, rad=-0.2)
    arrow(ax, (56, H - 35), (56, H - 10), text="5 polls H ≥ 0.95", color=GREEN, fs=4.6, toff=(-1, 0))
    arrow(ax, (64, H - 10), (64, H - 35), text="3 polls\nH < 0.50", color=RED, fs=4.6, toff=(4, 0))
    arrow(ax, (32, H - 42.5), (50, H - 38.5), color=GREY, ls="--")
    save(fig, "Fig 12 Fault Detection Workflow")


def daly(c, m):
    if c >= 2 * m:
        return m
    r = c / (2 * m)
    return math.sqrt(2 * c * m) * (1 + math.sqrt(r) / 3 + r / 9) - c


def fig13():
    fig = plt.figure(figsize=(COL_W, 4.4))
    ax = fig.add_axes([0, 0.52, 1, 0.48])
    W, H = 100, 100 * (4.4 * 0.48) / COL_W
    ax.set_xlim(0, W)
    ax.set_ylim(0, H)
    ax.axis("off")
    ax.text(1, H - 1, "(a)", fontsize=7, fontweight="bold", va="top")
    lv = [("Task level", "Spark: retry tasks, recompute lost\npartitions from lineage", LGREEN, GREEN),
          ("Attempt level", "Controller: driver crashed on a healthy\ncluster → retry there, restore stages", LBLUE, BLUE),
          ("Cluster level", "Controller: cluster FAILED and job stalled\n→ new attempt on argmin J, restore stages", LRED, RED)]
    for i, (n, t, fc, ec) in enumerate(lv):
        y = H - 13 - i * 11
        box(ax, 8, y, 22, 9, n, fc=fc, ec=ec, fs=6, bold=True)
        box(ax, 32, y, 64, 9, t, fc="white", ec=ec, fs=5.2, align="left")
    ax.annotate("", xy=(4, H - 35), xytext=(4, H - 6), arrowprops=dict(arrowstyle="-|>", color=GREY, lw=0.8))
    ax.text(2.2, H - 21, "cost / scope", rotation=90, fontsize=5, color=GREY, va="center", ha="center")
    b = fig.add_axes([0.15, 0.08, 0.8, 0.38])
    ms = [60 * (1.08 ** k) for k in range(0, 65)]
    for c, col in ((2, GREEN), (5, BLUE), (10, RED)):
        taus = [daly(c, m) for m in ms]
        b.plot(ms, taus, color=col, lw=1, label=f"τ*, C = {c} s")
        b.plot(ms, [t / 2 + c for t in taus], color=col, lw=0.8, ls="--", label=f"W_lost, C = {c} s")
    b.set_xscale("log")
    b.set_yscale("log")
    b.set_xlabel("MTBF M (s)", fontsize=6)
    b.set_ylabel("seconds", fontsize=6)
    b.tick_params(labelsize=5)
    b.grid(True, which="both", lw=0.3, alpha=0.5)
    b.legend(fontsize=4.5, ncol=2, frameon=False, loc="upper left")
    b.set_title("(b) Daly optimum interval and expected lost work", fontsize=6, loc="left")
    for s in ("top", "right"):
        b.spines[s].set_visible(False)
    save(fig, "Fig 13 Fault Recovery Architecture")


def fig14():
    fig, ax, H = canvas(COL_W, 3.2)
    steps = [("t0", "fault: cluster A outage", LRED, RED),
             ("+0-1.5 s", "master probe times out", LORANGE, ORANGE),
             ("+6 s", "3 polls H < 0.50 → A FAILED (logged with causes)", LORANGE, ORANGE),
             ("+10 s stall", "driver reports no completed tasks", LORANGE, ORANGE),
             ("≈ +16 s", "kill driver; place argmin J_k → B (logged)", LGREEN, GREEN),
             ("", "spark-submit attempt n+1 on master B", LGREEN, GREEN),
             ("", "rds: restore committed stages, compute rest", LBLUE, BLUE),
             ("end", "job SUCCEEDED; reliability of A and B updated", LBLUE, BLUE)]
    for i, (t, s, fc, ec) in enumerate(steps):
        y = H - 7 - i * 7.6
        b = box(ax, 22, y, 74, 5.8, s, fc=fc, ec=ec, fs=5.2)
        ax.text(20, y + 2.9, t, ha="right", va="center", fontsize=5, color=GREY)
        if i < len(steps) - 1:
            arrow(ax, (59, y), (59, y - 1.8), color=GREY)
    save(fig, "Fig 14 Failover and Recovery Workflow")


def fig15():
    fig, ax, H = canvas(COL_W, 2.0)
    c = box(ax, 34, H - 14, 32, 10, "Controller\n(cluster view, job attempts)", fc=LGREEN, ec=GREEN, fs=5.5, bold=True)
    a = box(ax, 2, H - 34, 26, 10, "Cluster A", fc=LBLUE, ec=BLUE, fs=6, bold=True)
    b = box(ax, 72, H - 34, 26, 10, "Cluster B", fc=LBLUE, ec=BLUE, fs=6, bold=True)
    s = box(ax, 26, 2, 48, 9, "Object storage\njob state + commit markers", fc=LPURPLE, ec=PURPLE, fs=5.5)
    arrow(ax, (38, H - 14), (18, H - 24), text="probe · attempt", color=GREEN, fs=4.8)
    arrow(ax, (62, H - 14), (82, H - 24), text="probe · attempt", color=GREEN, fs=4.8)
    arrow(ax, (15, H - 34), (32, 11), color=PURPLE, both=True)
    arrow(ax, (85, H - 34), (68, 11), color=PURPLE, both=True)
    ax.plot([30, 70], [H - 29, H - 29], color=RED, lw=0.8, ls=":")
    ax.text(50, H - 27.5, "no direct coordination", ha="center", fontsize=5, color=RED)
    save(fig, "Fig 15 Multi-Cluster Coordination Model")


def fig16():
    fig, ax, H = canvas(COL_W, 1.4)
    trig = box(ax, 2, H - 10, 28, 7, "trigger: submit,\nretry, failover", fc=LORANGE, ec=ORANGE, fs=5.2)
    el = box(ax, 36, H - 10, 28, 7, "eligibility: drop\nFAILED / excluded", fc=LBLUE, ec=BLUE, fs=5.2)
    sc = box(ax, 70, H - 10, 28, 7, "score each cluster\nJ = αL + β(1−H) + γT", fc=LBLUE, ec=BLUE, fs=5.2)
    am = box(ax, 70, H - 24, 28, 7, "argmin J,\ntie → name order", fc=LBLUE, ec=BLUE, fs=5.2)
    lg = box(ax, 36, H - 24, 28, 7, "decision log:\nall J_k + reason", fc=LPURPLE, ec=PURPLE, fs=5.2)
    sb = box(ax, 2, H - 24, 28, 7, "spark-submit to\nchosen master", fc=LGREEN, ec=GREEN, fs=5.2)
    arrow(ax, mid(trig, "r"), mid(el, "l"))
    arrow(ax, mid(el, "r"), mid(sc, "l"))
    arrow(ax, mid(sc, "b"), mid(am, "t"))
    arrow(ax, mid(am, "l"), mid(lg, "r"))
    arrow(ax, mid(lg, "l"), mid(sb, "r"))
    box(ax, 2, 2, 96, 8, "α = 0.4 (load)   β = 0.5 (health)   γ = 0.1 (data transfer; 0 in testbed)\nno eligible cluster → job WAITS",
        fc="white", ec=GREY, fs=5.2)
    save(fig, "Fig 16 Workload Orchestration Framework")


def fig17():
    fig, ax, H = canvas(COL_W, 2.0)
    sig = ["unreachable", "workers_lost", "latency", "stall", "executor_loss"]
    for i, s in enumerate(sig):
        box(ax, 2, H - 8 - i * 6, 22, 5, f"a: {s}", fc=LBLUE, ec=BLUE, fs=4.8)
        arrow(ax, (24, H - 5.5 - i * 6), (32, H - 17), color=GREY, lw=0.5)
    c = box(ax, 32, H - 22, 26, 10, "contributions\nw_i · a_i\n(sum → H)", fc=LGREEN, ec=GREEN, fs=5.2)
    t = box(ax, 64, H - 12, 34, 8, "transition record\nstate, H, top causes", fc=LPURPLE, ec=PURPLE, fs=5)
    f = box(ax, 64, H - 24, 34, 8, "failover record\nsource, target, all J_k", fc=LPURPLE, ec=PURPLE, fs=5)
    r = box(ax, 32, 3, 38, 9, "reliability score R\navailability · recovery\nsuccess · health", fc=LORANGE, ec=ORANGE, fs=5)
    arrow(ax, mid(c, "r"), mid(t, "l"))
    arrow(ax, mid(c, "r"), mid(f, "l"))
    arrow(ax, mid(c, "b"), mid(r, "t"))
    o = box(ax, 76, 3, 22, 9, "API, Grafana,\naudit trail", fc="white", ec=GREY, fs=5)
    arrow(ax, mid(r, "r"), mid(o, "l"))
    save(fig, "Fig 17 Explainable Reliability Framework")


def fig18():
    fig, ax, H = canvas(COL_W, 1.7)
    group(ax, 24, 2, 74, H - 5, "Private container network", fc=LGREY, ec=GREY)
    box(ax, 27, H - 15, 30, 7, "Spark clusters", fc=LBLUE, ec=BLUE, fs=5.3)
    box(ax, 65, H - 15, 30, 7, "Object storage", fc=LPURPLE, ec=PURPLE, fs=5.3)
    box(ax, 27, H - 28, 30, 9, "Controller API\n+ decision log (audit)", fc=LGREEN, ec=GREEN, fs=5.2)
    box(ax, 65, H - 28, 30, 9, "credentials /\nsecret store", fc="white", ec=GREY, fs=5.2, ls="--")
    box(ax, 27, 5, 68, 7, "TLS · Spark auth · bucket policies · non-root (designed)", fc="white", ec=RED, fs=5, ls="--")
    box(ax, 1, H - 15, 20, 7, "users\n(roles)", fc=LORANGE, ec=ORANGE, fs=5.2)
    box(ax, 1, H - 28, 20, 7, "identity\nprovider", fc="white", ec=ORANGE, fs=5.2, ls="--")
    arrow(ax, (21, H - 11.5), (27, H - 23), color=ORANGE, text="RBAC", fs=4.6)
    ax.text(60, H - 1.5, "solid: implemented   dashed: designed", ha="center", va="top", fontsize=5, color=GREY)
    save(fig, "Fig 18 Security and Governance Architecture")


def fig19():
    fig, ax, H = canvas(WIDE_W, 2.8)
    group(ax, 1, 1, 98, H - 3, "Host: 12 logical CPUs, 16 GB RAM, Windows 11, Docker 28.3 (WSL2, 12 GB)", fc=LGREY,
          ec=GREY, fs=6)
    for k, (x, n) in enumerate(((3, "A"), (27, "B"))):
        group(ax, x, H - 22, 22, 17, f"cluster {n}", fc=LBLUE, ec=BLUE, tc=BLUE)
        box(ax, x + 2, H - 12, 18, 4, f"master {n} (768 MB)", fc="white", ec=BLUE, fs=5)
        box(ax, x + 1.5, H - 20, 9, 6, f"worker\n2c/1.75 GB", fc="white", ec=BLUE, fs=4.6)
        box(ax, x + 11.5, H - 20, 9, 6, f"worker\n2c/1.75 GB", fc="white", ec=BLUE, fs=4.6)
    group(ax, 52, H - 22, 26, 17, "controller (2.5 GB)", fc=LGREEN, ec=GREEN, tc=GREEN)
    box(ax, 54, H - 12, 22, 4, "drivers + rds", fc="white", ec=GREEN, fs=5)
    box(ax, 54, H - 17, 22, 4, "experiment runner", fc="white", ec=GREEN, fs=5)
    box(ax, 54, H - 21.5, 22, 3.8, "fault injector", fc="white", ec=RED, fs=5)
    box(ax, 81, H - 10, 16, 5, "MinIO (512 MB)", fc=LPURPLE, ec=PURPLE, fs=5)
    box(ax, 81, H - 16, 16, 5, "Prometheus", fc=LORANGE, ec=ORANGE, fs=5)
    box(ax, 81, H - 22, 16, 5, "Grafana", fc=LORANGE, ec=ORANGE, fs=5)
    box(ax, 3, 3, 75, 5, "Docker Engine API  ←  fault injector: kill · pause · tc netem · network disconnect · cpu quota",
        fc="white", ec=RED, fs=5.2, ls="--")
    box(ax, 81, 3, 16, 5, "bridge network rmc-net", fc="white", ec=GREY, fs=4.8)
    save(fig, "Fig 19 Experimental Testbed Architecture")


def fig20():
    fig, ax, H = canvas(WIDE_W, 2.2)
    raw = ["runs.csv", "decisions.jsonl", "events/*.jsonl", "cluster_timeseries.csv"]
    met = ["job: success, duration,\ndelay, downtime", "recovery: detection,\nfailover, streaming", "work: recomputed,\ncheckpoint cost",
           "resource: utilisation U"]
    for i, (r, m) in enumerate(zip(raw, met)):
        y = H - 7 - i * 6.5
        box(ax, 2, y, 20, 5, r, fc=LORANGE, ec=ORANGE, fs=5.2)
        box(ax, 30, y, 26, 5, m, fc=LBLUE, ec=BLUE, fs=4.8)
        arrow(ax, (22, y + 2.5), (30, y + 2.5), color=GREY)
        arrow(ax, (56, y + 2.5), (63, H / 2 - 1), color=GREY, lw=0.5)
    st = box(ax, 63, H / 2 - 7, 16, 12, "statistics\nMann-Whitney U\nCliff's δ\nbootstrap CI", fc=LGREEN, ec=GREEN, fs=5)
    out = box(ax, 84, H / 2 - 7, 14, 12, "Tables 11-12\nFigs 21-24", fc=LPURPLE, ec=PURPLE, fs=5.2, bold=True)
    arrow(ax, mid(st, "r"), mid(out, "l"))
    save(fig, "Fig 20 Evaluation Framework")


def placeholder(name, label, width=WIDE_W, height=2.6):
    fig, ax, H = canvas(width, height)
    box(ax, 2, 2, 96, H - 4, "", fc="#FAFAFA", ec=GREY, ls="--")
    ax.text(50, H / 2 + 4, label, ha="center", va="center", fontsize=8, color=GREY, fontweight="bold")
    ax.text(50, H / 2 - 4, "PLACEHOLDER - replace with the figure produced by analysis/report.py\nafter running the experiments (README Steps 6-8)",
            ha="center", va="center", fontsize=6, color=RED)
    save(fig, name)


def fig25():
    fig, ax, H = canvas(COL_W, 1.5)
    y = H - 14
    segs = [(2, 30, "normal\nprocessing", LGREEN, GREEN), (30, 44, "detect", LORANGE, ORANGE),
            (44, 64, "migrate +\nrestart", LORANGE, ORANGE), (64, 98, "resumed on B", LGREEN, GREEN)]
    for a, b, t, fc, ec in segs:
        box(ax, a, y, b - a, 7, t, fc=fc, ec=ec, fs=5, rounding=0.3)
    ax.plot([30, 30], [y - 3, y + 10], color=RED, lw=0.9)
    ax.text(30, y + 11, "failure", ha="center", fontsize=5.2, color=RED)
    ax.plot([18, 18], [y - 3, y + 10], color=PURPLE, lw=0.8, ls="--")
    ax.text(18, y + 11, "last commit", ha="center", fontsize=5, color=PURPLE)
    arrow(ax, (18, y - 4), (30, y - 4), text="RPO (work)", color=PURPLE, fs=4.8, both=True, toff=(0, -2))
    arrow(ax, (30, y - 4), (64, y - 4), text="RTO", color=RED, fs=4.8, both=True, toff=(0, -2))
    box(ax, 2, 2, 96, 12, "bounded by: detection (3 polls) + stall rule (10 s) + driver start-up  →  RTO\n"
        "adaptive checkpoints (τ*) + stage length  →  RPO\nevidence: decision log, stage events, Table 13",
        fc="white", ec=GREY, fs=5, align="left")
    save(fig, "Fig 25 Business Continuity Framework")


def fig26():
    fig, ax, H = canvas(COL_W, 1.9)
    box(ax, 2, H - 9, 30, 6, "card transactions", fc=LORANGE, ec=ORANGE, fs=5.3)
    group(ax, 2, H - 30, 46, 18, "AZ 1: cluster A (primary)", fc=LBLUE, ec=BLUE, tc=BLUE, fs=5.3)
    group(ax, 52, H - 30, 46, 18, "AZ 2: cluster B (standby + work)", fc=LBLUE, ec=BLUE, tc=BLUE, fs=5.3)
    for x in (4, 54):
        box(ax, x, H - 27, 13, 9, "features", fc="white", ec=GREEN, fs=5)
        box(ax, x + 15, H - 27, 13, 9, "model\nscore", fc="white", ec=GREEN, fs=5)
        box(ax, x + 30, H - 27, 12, 9, "alerts", fc="white", ec=GREEN, fs=5)
    box(ax, 2, 2, 60, 8, "replicated object storage: features, models, commits", fc=LPURPLE, ec=PURPLE, fs=5)
    box(ax, 66, 2, 32, 8, "RMC-Spark controller\n+ audit log", fc=LGREEN, ec=GREEN, fs=5)
    arrow(ax, (17, H - 9), (17, H - 12), color=ORANGE)
    arrow(ax, (48, H - 21), (52, H - 21), color=RED, ls="--", text="failover", fs=4.6)
    save(fig, "Fig 26 Financial Analytics Resilience Architecture")


def fig27():
    fig, ax, H = canvas(COL_W, 1.6)
    box(ax, 2, H - 9, 22, 6, "machine\nsensors", fc=LORANGE, ec=ORANGE, fs=5.2)
    box(ax, 28, H - 9, 22, 6, "stream\ningestion", fc=LORANGE, ec=ORANGE, fs=5.2)
    a = box(ax, 54, H - 9, 44, 6, "streaming anomaly job (W4 pattern)", fc=LGREEN, ec=GREEN, fs=5.2)
    b = box(ax, 54, H - 19, 44, 6, "PdM training job, AI4I (W2 pattern)", fc=LGREEN, ec=GREEN, fs=5.2)
    c = box(ax, 54, H - 29, 44, 6, "maintenance planning dashboard", fc="white", ec=GREY, fs=5.2)
    arrow(ax, (24, H - 6), (28, H - 6))
    arrow(ax, (50, H - 6), (54, H - 6))
    arrow(ax, (39, H - 9), (54, H - 16), color=GREY)
    arrow(ax, mid(b, "b"), mid(c, "t"))
    box(ax, 2, 2, 96, 9, "resilient multi-cluster Spark: clusters A + B, shared storage, controller", fc=LBLUE, ec=BLUE, fs=5.3,
        bold=True)
    save(fig, "Fig 27 Smart Manufacturing Analytics Platform")


def fig29():
    fig, ax, H = canvas(COL_W, 1.9)
    cols = [("Short term", ["sensitivity analysis\nof thresholds", "idempotency keys for\nside effects"]),
            ("Medium term", ["replicated controller\n(leader election)", "replicated object\nstorage"]),
            ("Long term", ["multi-host / cloud\nevaluation", "transfer-aware geo\nplacement"])]
    for i, (t, items) in enumerate(cols):
        x = 2 + i * 33
        ax.text(x + 15, H - 2, t, ha="center", va="top", fontsize=6, fontweight="bold", color=BLUE)
        for j, it in enumerate(items):
            box(ax, x, H - 17 - j * 13, 30, 11, it, fc=[LGREEN, LORANGE, LPURPLE][i], ec=[GREEN, ORANGE, PURPLE][i], fs=5)
    box(ax, 2, 2, 96, 6, "limitations: single host · controller & MinIO SPOF · at-least-once · untuned thresholds",
        fc=LRED, ec=RED, fs=5)
    save(fig, "Fig 29 Challenges and Limitations Roadmap")


def fig30():
    fig, ax, H = canvas(COL_W, 1.45)
    ax.annotate("", xy=(98, 8), xytext=(2, 8), arrowprops=dict(arrowstyle="-|>", color=BLUE, lw=1))
    items = [("predictive\nsignals", LBLUE, BLUE), ("Kubernetes /\nserverless back-ends", LGREEN, GREEN),
             ("federated\nclusters", LORANGE, ORANGE), ("agentic, explainable\norchestration", LPURPLE, PURPLE)]
    for i, (t, fc, ec) in enumerate(items):
        x = 4 + i * 24
        box(ax, x, 14 + i * 5, 21, 10, t, fc=fc, ec=ec, fs=4.7, bold=True)
        ax.plot([x + 10.5], [8], "o", color=ec, ms=3)
        ax.plot([x + 10.5, x + 10.5], [8, 14 + i * 5], color=ec, lw=0.5)
    ax.text(50, 3, "increasing autonomy, scope and scale", ha="center", fontsize=5.5, color=BLUE, style="italic")
    save(fig, "Fig 30 Future Research Roadmap")


def fig31():
    fig, ax, H = canvas(COL_W, 1.9)
    box(ax, 2, H - 9, 30, 6, "predictive models\n(failure, workload)", fc=LBLUE, ec=BLUE, fs=5)
    box(ax, 68, H - 9, 30, 6, "LLM advisory agent\n(reads decision log)", fc=LPURPLE, ec=PURPLE, fs=5)
    ctl = box(ax, 26, H - 22, 48, 8, "deterministic explainable controller\n(health, failover, placement)", fc=LGREEN,
              ec=GREEN, fs=5.3, bold=True)
    arrow(ax, (17, H - 9), (35, H - 14), text="extra signal", fs=4.5)
    arrow(ax, (83, H - 9), (65, H - 14), text="proposals", fs=4.5, ls="--")
    for i, t in enumerate(["standalone\nSpark", "Kubernetes\nSpark", "serverless\nanalytics", "partner\nfederation"]):
        b = box(ax, 2 + i * 24.5, H - 36, 22, 9, t, fc="white", ec=BLUE, fs=5)
        arrow(ax, (50, H - 22), mid(b, "t"), color=GREY, lw=0.5)
    box(ax, 2, 2, 96, 6, "replicated, policy-aware storage plane", fc=LPURPLE, ec=PURPLE, fs=5.3)
    save(fig, "Fig 31 Next-Generation Resilient Analytics Architecture")


def fig32():
    fig, ax, H = canvas(COL_W, 1.7)
    probs = ["cluster outage", "long lineage", "gray failures", "unneeded restarts", "opaque decisions"]
    comps = ["C3 failover", "C2 adaptive ckpt", "C1 health signals", "progress-aware rule", "C5 explanations"]
    evid = ["success rate", "recomputed work", "detection latency", "keep decisions", "decision log"]
    for col, (items, fc, ec, t) in enumerate(((probs, LRED, RED, "Problems"), (comps, LGREEN, GREEN, "Contributions"),
                                              (evid, LBLUE, BLUE, "Evidence"))):
        x = 2 + col * 34
        ax.text(x + 14, H - 1.5, t, ha="center", va="top", fontsize=6, fontweight="bold", color=ec)
        for j, it in enumerate(items):
            box(ax, x, H - 10 - j * 7.5, 28, 5.5, it, fc=fc, ec=ec, fs=5)
            if col < 2:
                arrow(ax, (x + 28, H - 7.25 - j * 7.5), (x + 34, H - 7.25 - j * 7.5), color=GREY)
    box(ax, 2, 2, 96, 5, "rds library + open testbed + reproducible evaluation", fc=LORANGE, ec=ORANGE, fs=5.3, bold=True)
    save(fig, "Fig 32 Research Contribution Framework")


def main():
    for f in (fig01, fig02, fig03, fig04, fig05, fig06, fig07, fig08, fig09, fig10, fig11, fig12, fig13, fig14, fig15,
              fig16, fig17, fig18, fig19, fig20, fig25, fig26, fig27, fig29, fig30, fig31, fig32):
        f()
    placeholder("Fig 21 Fault Recovery Performance", "Fig. 21  Fault recovery performance (downtime per fault and configuration)")
    placeholder("Fig 22 Availability and Uptime Evaluation", "Fig. 22  Availability and success rate per configuration")
    placeholder("Fig 23 Resource Utilization and Cluster Stability", "Fig. 23  Utilisation and health during a cluster outage")
    placeholder("Fig 24 Comparative Benchmark Analysis", "Fig. 24  Comparative radar chart", width=COL_W, height=3.0)
    placeholder("Fig 28 Business Impact Dashboard", "Fig. 28  Business impact dashboard", width=COL_W, height=2.4)
    print("figures written to", OUT, len(os.listdir(OUT)))


if __name__ == "__main__":
    main()
