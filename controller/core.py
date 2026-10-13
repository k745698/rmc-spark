"""The resilience controller: monitor -> assess -> detect -> decide -> act, once per poll interval."""
from __future__ import annotations

import csv
import os
import threading
import time

from .decisions import DecisionLog
from .health import HealthModel, Observation
from .jobs import (FAILED_JOB, RUNNING, SUCCEEDED, TERMINAL, WAITING, JobManager, JobRun, JobSpec,
                   on_attempt_exit, while_running)
from .monitor import probe_master
from .orchestrator import ClusterView, place
from .reliability import ClusterReliability, system_mtbf
from .statemachine import FAILED, HEALTHY, HealthStateMachine, TimeoutDetector


class ClusterRuntime:
    def __init__(self, name: str, ccfg: dict, ctl: dict, now: float):
        self.name = name
        self.cfg = ccfg
        self.health_model = HealthModel(ctl["health_weights"], ccfg["expected_workers"],
                                        alpha=ctl["latency_ewma_alpha"], z_low=ctl["latency_z_low"],
                                        z_high=ctl["latency_z_high"], stall_limit_s=ctl["stall_limit_s"])
        self.smart = HealthStateMachine(name, ctl["suspect_threshold"], ctl["failed_threshold"],
                                        ctl["failed_consecutive"], ctl["recovered_consecutive"])
        self.naive = TimeoutDetector(name, ctl["naive_timeout_s"])
        self.reliability = ClusterReliability(name, ctl["mtbf_prior_s"], ctl["mtbf_prior_weight"], now)
        self.obs: Observation | None = None
        self.report = None

    def state(self, mode: str) -> str:
        if mode == "smart":
            return self.smart.state
        if mode == "naive":
            return self.naive.state
        return HEALTHY   # mode none: nobody watches the cluster


class Controller:
    def __init__(self, cfg: dict, decisions_file: str | None = None, timeseries_file: str | None = None,
                 logs_dir: str | None = None, events_dir: str | None = None, probe=probe_master):
        self.cfg = cfg
        self.ctl = cfg["controller"]
        paths = cfg["paths"]
        now = time.time()
        self.decisions = DecisionLog(decisions_file or paths["decisions_file"])
        self.events_dir = events_dir or paths["events_dir"]
        self.jobs = JobManager(cfg, self.decisions, logs_dir or paths["logs_dir"], self.events_dir)
        self.clusters = {n: ClusterRuntime(n, c, self.ctl, now) for n, c in cfg["clusters"].items()}
        self.order = list(cfg["clusters"])
        self.probe = probe
        self.lock = threading.RLock()
        self.failovers_total = 0
        self.listeners = []            # callables(controller) after each tick (e.g. Prometheus export)
        self._ts_path = timeseries_file or paths["timeseries_file"]
        os.makedirs(os.path.dirname(self._ts_path), exist_ok=True)
        if not os.path.exists(self._ts_path):
            with open(self._ts_path, "w", newline="", encoding="utf-8") as fh:
                csv.writer(fh).writerow(["ts", "cluster", "reachable", "latency_s", "alive_workers", "cores",
                                         "cores_used", "health", "state_smart", "state_naive", "running_jobs"])

    # ------------------------------------------------------------------ public API
    def mtbf(self) -> float:
        return system_mtbf([c.reliability for c in self.clusters.values()])

    def submit(self, spec: JobSpec, now: float | None = None) -> JobRun:
        now = time.time() if now is None else now
        with self.lock:
            if spec.job_id in self.jobs.jobs:
                raise ValueError(f"duplicate job id {spec.job_id}")
            run = JobRun(spec=spec, submitted=now)
            self.jobs.jobs[spec.job_id] = run
            target, reason = self._initial_cluster(spec)
            if target is None:
                run.state = WAITING
                self.decisions.log("wait", ts=now, job_id=spec.job_id, reason=reason)
            else:
                self.jobs.start_attempt(run, target, self.mtbf(), now, reason)
            return run

    def tick(self, now: float | None = None) -> None:
        now = time.time() if now is None else now
        with self.lock:
            self.jobs.refresh_progress(now)
            for cr in self.clusters.values():
                self._assess_cluster(cr, now)
            for run in list(self.jobs.jobs.values()):
                if run.state not in TERMINAL:
                    self._manage_job(run, now)
        for fn in self.listeners:
            try:
                fn(self)
            except Exception:   # monitoring export must never break the control loop
                pass

    def run_forever(self, stop_event: threading.Event) -> None:
        while not stop_event.is_set():
            t0 = time.time()
            self.tick(t0)
            stop_event.wait(max(0.0, self.ctl["poll_interval_s"] - (time.time() - t0)))

    # ------------------------------------------------------------------ monitoring + detection
    def _assess_cluster(self, cr: ClusterRuntime, now: float) -> None:
        obs = self.probe(cr.cfg["ui_url"], self.ctl["probe_timeout_s"])
        obs.ts = now
        running = self.jobs.running_on(cr.name)
        if running:
            obs.stall_s = max(self.jobs.stall_s(r.current, now) for r in running)
            obs.executors_lost = sum(r.current.lost_execs for r in running)
            obs.executors_expected = sum(max(r.current.seen_execs, 1) for r in running)
        rep = cr.health_model.assess(obs)
        cr.obs, cr.report = obs, rep
        causes = ", ".join(f"{k}={v}" for k, v in rep.top_causes())
        transitions = (("health", cr.smart.update(now, rep.health, causes)),
                       ("timeout", cr.naive.update(now, obs.reachable)))
        for detector, tr in transitions:
            if tr is not None:
                self.decisions.log("transition", ts=now, cluster=tr.cluster, detector=detector,
                                   old=tr.old, new=tr.new, reason=tr.reason, health=round(rep.health, 3),
                                   contributions={k: round(v, 3) for k, v in rep.contributions.items()})
        cr.reliability.observe(now, cr.smart.state == FAILED, rep.health)
        with open(self._ts_path, "a", newline="", encoding="utf-8") as fh:
            csv.writer(fh).writerow([round(now, 3), cr.name, int(obs.reachable), round(obs.latency_s, 4),
                                     obs.alive_workers, obs.cores, obs.cores_used, round(rep.health, 4),
                                     cr.smart.state, cr.naive.state, len(running)])

    # ------------------------------------------------------------------ placement
    def _views(self, mode: str) -> list:
        out = []
        for name in self.order:
            cr = self.clusters[name]
            obs = cr.obs
            out.append(ClusterView(name=name, state=cr.state(mode),
                                   health=cr.report.health if cr.report else 1.0,
                                   cores=obs.cores if obs else 0, cores_used=obs.cores_used if obs else 0))
        return out

    def _initial_cluster(self, spec: JobSpec):
        if spec.home_cluster:
            return spec.home_cluster, f"home cluster {spec.home_cluster}"
        if spec.mode == "smart":
            p = self._place(spec.mode)
            return p.cluster, p.reason
        return self.order[0], f"default cluster {self.order[0]}"

    def _place(self, mode: str, exclude: tuple = ()):
        pc = self.ctl["placement"]
        return place(self._views(mode), pc["alpha"], pc["beta"], pc["gamma"], exclude=exclude)

    def _failover_target(self, mode: str, current: str):
        if mode == "smart":
            p = self._place(mode, exclude=(current,))
            return p.cluster, p.reason
        # naive active/passive: next cluster in fixed order that its detector does not consider failed
        idx = self.order.index(current)
        for name in self.order[idx + 1:] + self.order[:idx]:
            if self.clusters[name].state(mode) != FAILED:
                return name, f"passive cluster {name}"
        return None, "no passive cluster available"

    # ------------------------------------------------------------------ recovery actions
    def _manage_job(self, run: JobRun, now: float) -> None:
        spec, att = run.spec, run.current
        if now - run.submitted > spec.deadline_s:
            if att is not None and att.ended is None:
                self.jobs.kill_attempt(att, "deadline", now)
            self._finish(run, FAILED_JOB, f"deadline {spec.deadline_s:.0f}s exceeded", now)
            return

        if run.state == WAITING:
            target, reason = (self._failover_target(spec.mode, att.cluster) if att
                              else self._initial_cluster(spec))
            if target is not None:
                self.jobs.start_attempt(run, target, self.mtbf(), now, f"resume: {reason}")
            return

        cr = self.clusters[att.cluster]
        state = cr.state(spec.mode)
        code = att.proc.poll() if att.proc is not None else None

        if code is not None:                                   # the driver exited
            self.jobs._close(att, now, "exit")
            retries_here = sum(1 for a in run.attempts if a.cluster == att.cluster) - 1
            action = on_attempt_exit(spec.mode, code, state, retries_here,
                                     self.ctl["max_retries_same_cluster"])
            if action == "succeed":
                cr.reliability.record_job(True)
                self._finish(run, SUCCEEDED, "completed", now)
            elif action == "fail":
                cr.reliability.record_job(False)
                self._finish(run, FAILED_JOB, f"driver exit code {code}", now)
            elif action == "retry":
                cr.reliability.record_job(False)
                run.retries += 1
                self.jobs.start_attempt(run, att.cluster, self.mtbf(), now,
                                        f"retry on healthy cluster after exit code {code}")
            else:
                cr.reliability.record_job(False)
                self._failover(run, now, f"driver exit code {code} on {state} cluster")
            return

        decision = while_running(spec.mode, state, self.jobs.stall_s(att, now), self.ctl["migrate_stall_s"])
        if decision == "migrate":
            self.jobs.kill_attempt(att, "migrated", now)
            cr.reliability.record_job(False)
            self._failover(run, now, f"cluster {att.cluster} {state}, no progress for "
                                     f"{self.jobs.stall_s(att, now):.0f}s")
        elif decision == "keep" and not run.kept_logged:
            run.kept_logged = True
            self.decisions.log("keep", ts=now, job_id=spec.job_id, cluster=att.cluster,
                               reason="cluster FAILED but job still making progress -> not migrated")

    def _failover(self, run: JobRun, now: float, why: str) -> None:
        current = run.current.cluster
        target, reason = self._failover_target(run.spec.mode, current)
        run.failovers += 1
        self.failovers_total += 1
        self.decisions.log("failover", ts=now, job_id=run.spec.job_id, source=current, target=target,
                           reason=f"{why}; {reason}")
        if target is None:
            run.state = WAITING
        else:
            self.jobs.start_attempt(run, target, self.mtbf(), now, f"failover from {current}: {reason}")

    def _finish(self, run: JobRun, state: str, outcome: str, now: float) -> None:
        run.state, run.outcome, run.finished = state, outcome, now
        self.decisions.log("job_end", ts=now, job_id=run.spec.job_id, state=state, outcome=outcome,
                           attempts=len(run.attempts), failovers=run.failovers,
                           duration_s=round(now - run.submitted, 2))

    # ------------------------------------------------------------------ snapshots for API/metrics
    def snapshot(self) -> dict:
        with self.lock:
            clusters = {}
            for n, cr in self.clusters.items():
                rep = cr.report
                clusters[n] = {
                    "state_smart": cr.smart.state, "state_naive": cr.naive.state,
                    "health": rep.health if rep else None,
                    "anomalies": rep.anomalies if rep else None,
                    "top_causes": rep.top_causes(3) if rep else [],
                    "alive_workers": cr.obs.alive_workers if cr.obs else None,
                    "cores": cr.obs.cores if cr.obs else None,
                    "cores_used": cr.obs.cores_used if cr.obs else None,
                    "reliability": cr.reliability.score(self.ctl["reliability_weights"],
                                                        self.ctl["mttr_reference_s"]),
                }
            jobs = {jid: {"state": r.state, "outcome": r.outcome, "attempts": len(r.attempts),
                          "failovers": r.failovers, "cluster": r.current.cluster if r.current else None}
                    for jid, r in self.jobs.jobs.items()}
            return {"clusters": clusters, "jobs": jobs, "failovers_total": self.failovers_total,
                    "mtbf_s": self.mtbf()}
