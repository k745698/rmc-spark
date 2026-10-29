"""Measure the clean runtime of each workload in an experiment config and rewrite its timing fields.

    docker compose exec controller python -m experiments.calibrate experiments/configs/minimum.yaml

For every workload: run it `--runs` times without faults (vanilla Spark, no checkpoints), take the
median duration d, then set   expected_runtime_s = d,  fault_at_s = 0.4 d,  deadline_s = 3 d.
The calibration runs are kept in results/raw/calibration/ (they are not part of the experiment).
"""
from __future__ import annotations

import argparse
import csv
import statistics
import subprocess
import sys

import yaml


def main():
    p = argparse.ArgumentParser()
    p.add_argument("experiment")
    p.add_argument("--runs", type=int, default=2)
    p.add_argument("--fault-fraction", type=float, default=0.4)
    p.add_argument("--deadline-factor", type=float, default=3.0)
    a = p.parse_args()

    with open(a.experiment, encoding="utf-8") as fh:
        exp = yaml.safe_load(fh)

    calib = {
        "name": "calibration", "output_dir": "results/raw/calibration", "repetitions": a.runs, "seed": 1,
        "cooldown_s": 3, "transient_duration_s": 60,
        "systems": {"B1_vanilla": {"mode": "none", "policy": "never"}},
        "workloads": {w: {"deadline_s": 900, "fault_at_s": 99999, "expected_runtime_s": v.get("expected_runtime_s", 120)}
                      for w, v in exp["workloads"].items()},
        "faults": ["none"],
    }
    path = "experiments/configs/_calibration.yaml"
    with open(path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(calib, fh, sort_keys=False)
    subprocess.run([sys.executable, "-m", "experiments.run_matrix", path], check=True)

    durations = {}
    with open("results/raw/calibration/runs.csv", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row["state"] == "SUCCEEDED" and row["workload"] in exp["workloads"]:
                durations.setdefault(row["workload"], []).append(float(row["duration_s"]))

    for w, cfg in exp["workloads"].items():
        if w not in durations:
            raise SystemExit(f"calibration of {w} failed - check results/raw/calibration/logs")
        d = statistics.median(durations[w][-a.runs:])
        cfg["expected_runtime_s"] = round(d)
        cfg["fault_at_s"] = round(a.fault_fraction * d)
        cfg["deadline_s"] = round(a.deadline_factor * d)
        print(f"{w}: clean runtime {d:.1f} s -> fault_at_s={cfg['fault_at_s']}, deadline_s={cfg['deadline_s']}")

    with open(a.experiment, "w", encoding="utf-8") as fh:
        fh.write("# timing fields set by experiments/calibrate.py from measured clean runtimes\n")
        yaml.safe_dump(exp, fh, sort_keys=False)
    print(f"updated {a.experiment}")


if __name__ == "__main__":
    main()
