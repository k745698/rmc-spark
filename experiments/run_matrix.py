"""Run the experiment matrix  systems x workloads x faults x repetitions  and record raw results.

    docker compose exec controller python -m experiments.run_matrix experiments/configs/smoke.yaml
    docker compose exec controller python -m experiments.run_matrix experiments/configs/full.yaml --dry-run

Writes to <output_dir>/: runs.csv, decisions.jsonl, cluster_timeseries.csv, events/*.jsonl, logs/*.log
Runs are shuffled within each repetition (fixed seed) so slow drift of the laptop does not
favour one system. A run that crashes the runner itself is recorded with state RUNNER_ERROR.
"""
from __future__ import annotations

import argparse
import csv
import itertools
import json
import os
import random
import time
import traceback
import uuid

import yaml

from chaos.inject import FaultInjector
from controller.config import load_config
from controller.core import Controller
from controller.jobs import TERMINAL, JobSpec
from controller.statemachine import FAILED, HEALTHY
from controller.workloads import WORKLOADS

FIELDS = ["run_id", "rep", "system", "mode", "policy", "workload", "fault", "job_id", "t_submit", "t_fault",
          "t_detect", "t_action", "t_end", "duration_s", "state", "outcome", "attempts", "failovers",
          "retries", "clusters", "fault_target", "mtbf_at_submit_s"]


def wait_healthy(ctrl: Controller, timeout_s: float = 240.0) -> bool:
    """Tick until every cluster is reachable with all workers and its health detector says HEALTHY."""
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        ctrl.tick()
        ok = all(cr.obs and cr.obs.reachable and cr.obs.alive_workers >= cr.cfg["expected_workers"]
                 and cr.smart.state == HEALTHY for cr in ctrl.clusters.values())
        if ok:
            return True
        time.sleep(ctrl.ctl["poll_interval_s"])
    return False


def first_after(decisions: list, t: float, pred) -> float | None:
    for d in decisions:
        if d["ts"] >= t and pred(d):
            return d["ts"]
    return None


def run_one(ctrl, inj, exp, system, sname, workload, wname, fault, rep) -> dict:
    w = WORKLOADS[wname]
    job_id = f"{sname}-{wname}-{fault}-r{rep}-{uuid.uuid4().hex[:6]}"
    spec = JobSpec(job_id=job_id, script=w["script"], args=list(w.get("args", [])) + workload.get("args", []),
                   policy=system["policy"], mode=system["mode"], deadline_s=workload["deadline_s"],
                   extra_conf={**w.get("conf", {}), **system.get("conf", {})}, home_cluster="A")
    mtbf0 = ctrl.mtbf()
    t_submit = time.time()
    run = ctrl.submit(spec, t_submit)
    fault_at = workload["fault_at_s"]
    t_fault, target = None, None
    poll = ctrl.ctl["poll_interval_s"]

    while run.state not in TERMINAL:
        now = time.time()
        ctrl.tick(now)
        if fault != "none" and t_fault is None and now - t_submit >= fault_at and run.current:
            target = run.current.cluster
            info = inj.inject(fault, target, duration_s=exp.get("transient_duration_s", 60),
                              controller=ctrl, job_id=job_id)
            t_fault = time.time()
            ctrl.decisions.log("fault_injected", ts=t_fault, fault=fault, cluster=target, job_id=job_id,
                               info={k: v for k, v in info.items() if k != "output"})
        time.sleep(max(0.0, poll - (time.time() - now)))

    recent = [d for d in ctrl.decisions.recent if d["ts"] >= t_submit]
    t_detect = t_action = None
    if t_fault is not None:
        t_detect = first_after(recent, t_fault, lambda d: d["kind"] == "transition" and d.get("cluster") == target
                               and d.get("new") == FAILED
                               and d.get("detector") == ("timeout" if system["mode"] == "naive" else "health"))
        t_action = first_after(recent, t_fault, lambda d: d.get("job_id") == job_id
                               and d["kind"] in ("failover", "submit"))
    return {
        "run_id": uuid.uuid4().hex[:10], "rep": rep, "system": sname, "mode": system["mode"],
        "policy": system["policy"], "workload": wname, "fault": fault, "job_id": job_id,
        "t_submit": round(t_submit, 3), "t_fault": t_fault and round(t_fault, 3),
        "t_detect": t_detect and round(t_detect, 3), "t_action": t_action and round(t_action, 3),
        "t_end": round(run.finished, 3), "duration_s": round(run.finished - t_submit, 3),
        "state": run.state, "outcome": run.outcome, "attempts": len(run.attempts),
        "failovers": run.failovers, "retries": run.retries,
        "clusters": ">".join(a.cluster for a in run.attempts), "fault_target": target,
        "mtbf_at_submit_s": round(mtbf0, 1),
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("experiment", help="experiments/configs/<name>.yaml")
    p.add_argument("--config", default=None, help="cluster config (default $RMC_CONFIG)")
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()

    with open(a.experiment, encoding="utf-8") as fh:
        exp = yaml.safe_load(fh)
    cfg = load_config(a.config)
    combos = list(itertools.product(exp["systems"], exp["workloads"], exp["faults"]))
    reps = int(exp.get("repetitions", 1))
    total = len(combos) * reps
    est = sum(exp["workloads"][w]["expected_runtime_s"] for _, w, _ in combos) * reps
    print(f"{len(exp['systems'])} systems x {len(exp['workloads'])} workloads x {len(exp['faults'])} faults "
          f"x {reps} reps = {total} runs, roughly {est / 3600:.1f} h of job time (+ recovery/cool-down)")
    if a.dry_run:
        return

    out = exp["output_dir"]
    os.makedirs(out, exist_ok=True)
    ctrl = Controller(cfg, decisions_file=f"{out}/decisions.jsonl", timeseries_file=f"{out}/cluster_timeseries.csv",
                      logs_dir=f"{out}/logs", events_dir=os.path.abspath(f"{out}/events"))
    inj = FaultInjector(cfg)
    runs_csv = f"{out}/runs.csv"
    new_file = not os.path.exists(runs_csv)
    with open(f"{out}/experiment.json", "w", encoding="utf-8") as fh:
        json.dump({"experiment": exp, "cluster_config": cfg, "started": time.time()}, fh, indent=2, default=str)

    rng = random.Random(exp.get("seed", 2026))
    done = 0
    for rep in range(reps):
        order = combos[:]
        rng.shuffle(order)
        for sname, wname, fault in order:
            done += 1
            inj.restore_all()
            if not wait_healthy(ctrl):
                print("WARNING: clusters not healthy before run; continuing anyway")
            print(f"[{done}/{total}] rep={rep} system={sname} workload={wname} fault={fault}", flush=True)
            try:
                row = run_one(ctrl, inj, exp, exp["systems"][sname], sname, exp["workloads"][wname],
                              wname, fault, rep)
            except Exception as e:  # keep the matrix going; record the error
                traceback.print_exc()
                row = {k: None for k in FIELDS}
                row.update(rep=rep, system=sname, workload=wname, fault=fault, state="RUNNER_ERROR",
                           outcome=repr(e)[:200])
            print(f"    -> {row['state']} in {row.get('duration_s')} s, attempts={row.get('attempts')}, "
                  f"clusters={row.get('clusters')}", flush=True)
            with open(runs_csv, "a", newline="", encoding="utf-8") as fh:
                wr = csv.DictWriter(fh, fieldnames=FIELDS)
                if new_file:
                    wr.writeheader()
                    new_file = False
                wr.writerow(row)
            time.sleep(exp.get("cooldown_s", 10))
    inj.restore_all()
    print(f"done: {runs_csv}")


if __name__ == "__main__":
    main()
