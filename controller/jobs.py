"""Job manager: runs each job as a spark-submit driver (client mode, inside the controller
container) and applies the recovery policy of the system under test.

Recovery modes
  none   - vanilla Spark: no resubmission (baselines B1, B2)
  naive  - active/passive: master unreachable for naive_timeout_s -> rerun on the next cluster (B3)
  smart  - proposed: health state machine + progress-aware migration + J_k placement (P)
"""
from __future__ import annotations

import os
import signal
import subprocess
import time
from dataclasses import dataclass, field

from .monitor import probe_driver
from .statemachine import FAILED, SUSPECT

PENDING, RUNNING, WAITING, SUCCEEDED, FAILED_JOB = "PENDING", "RUNNING", "WAITING", "SUCCEEDED", "FAILED"
TERMINAL = (SUCCEEDED, FAILED_JOB)


@dataclass
class JobSpec:
    job_id: str
    script: str                      # e.g. jobs/etl_taxi.py (relative to /workspace)
    args: list = field(default_factory=list)
    policy: str = "never"            # rds checkpoint policy
    mode: str = "none"               # none | naive | smart
    deadline_s: float = 1800.0
    extra_conf: dict = field(default_factory=dict)
    home_cluster: str | None = None


@dataclass
class Attempt:
    n: int
    cluster: str
    ui_port: int
    started: float
    log_path: str
    proc: object = None
    ended: float | None = None
    exit_code: int | None = None
    end_reason: str = ""
    last_completed: int = -1
    last_progress_ts: float = 0.0
    lost_execs: int = 0
    seen_execs: int = 0


@dataclass
class JobRun:
    spec: JobSpec
    state: str = PENDING
    submitted: float = 0.0
    finished: float | None = None
    attempts: list = field(default_factory=list)
    failovers: int = 0
    retries: int = 0
    outcome: str = ""
    kept_logged: bool = False

    @property
    def current(self) -> Attempt | None:
        return self.attempts[-1] if self.attempts else None


# --------------------------------------------------------------------------- pure decision logic
def on_attempt_exit(mode: str, exit_code: int, cluster_state: str, retries_on_cluster: int,
                    max_retries: int) -> str:
    """What to do after a driver process exited. Returns 'succeed' | 'fail' | 'retry' | 'failover'."""
    if exit_code == 0:
        return "succeed"
    if mode == "none":
        return "fail"
    if mode == "naive":
        return "failover"
    # smart: crash on a healthy cluster -> retry there first (cheap: resumes from checkpoints)
    if cluster_state in (FAILED, SUSPECT) or retries_on_cluster >= max_retries:
        return "failover"
    return "retry"


def while_running(mode: str, cluster_state: str, stall_s: float, migrate_stall_s: float) -> str:
    """Decision for a live driver. Returns 'continue' | 'migrate' | 'keep'."""
    if cluster_state != FAILED or mode == "none":
        return "continue"
    if mode == "naive":
        return "migrate"
    return "migrate" if stall_s >= migrate_stall_s else "keep"


# --------------------------------------------------------------------------- process handling
class JobManager:
    def __init__(self, cfg: dict, decisions, logs_dir: str, events_dir: str):
        self.cfg = cfg
        self.sub = cfg["spark_submit"]
        self.ctl = cfg["controller"]
        self.decisions = decisions
        self.logs_dir = logs_dir
        self.events_dir = events_dir
        self.jobs: dict[str, JobRun] = {}
        self._ports_in_use = set()
        os.makedirs(logs_dir, exist_ok=True)

    # -------------------------------------------------- spark-submit
    def _alloc_port(self) -> int:
        base = int(self.sub.get("ui_port_base", 4040))
        for p in range(base, base + 10):
            if p not in self._ports_in_use:
                self._ports_in_use.add(p)
                return p
        raise RuntimeError("no free driver UI port (max 10 concurrent drivers)")

    def build_command(self, spec: JobSpec, cluster: str, attempt_n: int, ui_port: int, mtbf_s: float) -> list:
        c = self.cfg["clusters"][cluster]
        st = self.cfg["storage"]
        conf = {
            "spark.driver.host": "controller",
            "spark.driver.bindAddress": "0.0.0.0",
            "spark.ui.port": str(ui_port),
            "spark.port.maxRetries": "0",
            **{k: str(v) for k, v in spec.extra_conf.items()},
        }
        cmd = ["spark-submit", "--master", c["master_url"], "--deploy-mode", "client",
               "--name", f"{spec.job_id}-a{attempt_n}",
               "--driver-memory", self.sub["driver_memory"],
               "--executor-memory", self.sub["executor_memory"],
               "--executor-cores", str(self.sub["executor_cores"]),
               "--total-executor-cores", str(self.sub["total_executor_cores"])]
        for k, v in conf.items():
            cmd += ["--conf", f"{k}={v}"]
        cmd += [spec.script, "--job-id", spec.job_id, "--attempt", str(attempt_n), "--cluster", cluster,
                "--policy", spec.policy, "--mtbf", f"{mtbf_s:.1f}",
                "--checkpoint-root", st["checkpoint_root"], "--data-root", st["data_root"],
                "--results-root", st["results_root"], "--events-dir", self.events_dir]
        return cmd + list(spec.args)

    def start_attempt(self, run: JobRun, cluster: str, mtbf_s: float, now: float, reason: str) -> Attempt:
        n = len(run.attempts)
        port = self._alloc_port()
        log_path = os.path.join(self.logs_dir, f"{run.spec.job_id}.a{n}.{cluster}.log")
        cmd = self.build_command(run.spec, cluster, n, port, mtbf_s)
        fh = open(log_path, "w", encoding="utf-8")
        proc = subprocess.Popen(cmd, stdout=fh, stderr=subprocess.STDOUT, cwd="/workspace"
                                if os.path.isdir("/workspace") else None, start_new_session=True)
        att = Attempt(n=n, cluster=cluster, ui_port=port, started=now, log_path=log_path, proc=proc,
                      last_progress_ts=now)
        run.attempts.append(att)
        run.state = RUNNING
        self.decisions.log("submit", ts=now, job_id=run.spec.job_id, attempt=n, cluster=cluster,
                           mtbf_s=round(mtbf_s, 1), reason=reason)
        return att

    def kill_attempt(self, att: Attempt, reason: str, now: float, sig=signal.SIGTERM) -> None:
        if att.proc is not None and att.proc.poll() is None:
            try:
                os.killpg(att.proc.pid, sig)
                try:
                    att.proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(att.proc.pid, signal.SIGKILL)
                    att.proc.wait(timeout=10)
            except ProcessLookupError:
                pass
        self._close(att, now, reason)

    def _close(self, att: Attempt, now: float, reason: str) -> None:
        if att.ended is None:
            att.ended = now
            att.exit_code = att.proc.poll() if att.proc is not None else None
            att.end_reason = reason
            self._ports_in_use.discard(att.ui_port)

    def crash_driver(self, job_id: str) -> bool:
        """Fault injection: SIGKILL the driver as if it crashed (the manager sees a non-zero exit)."""
        run = self.jobs.get(job_id)
        att = run.current if run else None
        if att is None or att.proc is None or att.proc.poll() is not None:
            return False
        os.killpg(att.proc.pid, signal.SIGKILL)
        return True

    # -------------------------------------------------- progress
    def refresh_progress(self, now: float) -> None:
        for run in self.jobs.values():
            att = run.current
            if run.state != RUNNING or att is None or att.ended is not None:
                continue
            info = probe_driver(att.ui_port)
            if info is None:
                continue
            if info["completed"] != att.last_completed:
                att.last_completed = info["completed"]
                att.last_progress_ts = now
            att.lost_execs = info["lost_execs"]
            att.seen_execs = info["seen_execs"]

    def stall_s(self, att: Attempt, now: float) -> float:
        return max(0.0, now - att.last_progress_ts)

    def running_on(self, cluster: str) -> list:
        return [r for r in self.jobs.values()
                if r.state == RUNNING and r.current and r.current.cluster == cluster and r.current.ended is None]
