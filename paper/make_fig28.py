"""Fig 28 Business Impact Dashboard from the measured outage downtimes (results/report/runs_enriched.csv).

    python paper/make_fig28.py            (needs matplotlib and pandas; runs in the controller container)

Left: downtime avoided per year against B1 and B3 as a function of the outage rate N_f.
Right: break-even downtime cost C_d at which the avoided downtime pays for C_extra, Eq. (benefit).
"""
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
RUNS = os.path.join(HERE, "..", "results", "report", "runs_enriched.csv")
OUT = os.path.join(HERE, "Diagrams", "Fig 28 Business Impact Dashboard.png")

r = pd.read_csv(RUNS)
outage = r[r["fault"] == "cluster_outage"].groupby("system")["downtime_s"].mean()
d_rmc = outage["P_rmc"]
saved_h = {"vs B1 vanilla (lower bound)": (outage["B1_vanilla"] - d_rmc) / 3600,
           "vs B3 naive HA": (outage["B3_naive_ha"] - d_rmc) / 3600}

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8, "axes.spines.top": False,
                     "axes.spines.right": False})
fig, (a1, a2) = plt.subplots(1, 2, figsize=(7.0, 2.6))
nf = np.arange(1, 53)
for (label, h), c in zip(saved_h.items(), ["#2e8b57", "#e3a23b"]):
    a1.plot(nf, nf * h, color=c, label=f"{label}: {h * 3600:.0f} s per outage")
a1.set_xlabel("Cluster outages per year, N_f")
a1.set_ylabel("Downtime avoided per year (h)")
a1.set_title("(a) Downtime avoided", fontsize=8)
a1.legend(frameon=False, fontsize=7)

h = saved_h["vs B1 vanilla (lower bound)"]
for ce, ls in [(1_000, "-"), (10_000, "--"), (100_000, ":")]:
    a2.plot(nf, ce / (nf * h), color="#2e8b57", ls=ls, label=f"C_extra = {ce:,}")
a2.set_yscale("log")
a2.set_xlabel("Cluster outages per year, N_f")
a2.set_ylabel("Break-even C_d (per hour)")
a2.set_title("(b) Benefit positive above the line (vs B1)", fontsize=8)
a2.legend(frameon=False, fontsize=7)
fig.tight_layout()
fig.savefig(OUT, dpi=600)
print(f"D_base(B1)={outage['B1_vanilla']:.0f}s D_base(B3)={outage['B3_naive_ha']:.0f}s D_rmc={d_rmc:.0f}s -> {OUT}")
