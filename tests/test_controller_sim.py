"""End-to-end controller logic with a simulated clock, fake cluster probes and fake driver processes.

Scenario: a job runs on cluster A; at t=FAULT cluster A goes down completely (master unreachable,
executors gone). We check what each recovery mode does.
"""
import pytest

import controller.core as core
import controller.jobs as jobs
from controller.health import Observation
from controller.jobs import JobSpec

FAULT = 20.0


class FakeProc:
    _next_pid = 1000

    def __init__(self, cluster, world, start):
        self.cluster, self.world, self.start = cluster, world, start
        FakeProc._next_pid += 1
        self.pid = FakeProc._next_pid
        self.killed = False

    def poll(self):
        if self.killed:
            return -15
        # a driver on a dead cluster never finishes; a healthy one finishes after `runtime` seconds
        if self.world.up[self.cluster] and self.world.now - self.start >= self.world.runtime:
            return 0
        return None


class World:
    def __init__(self, runtime=60.0):
        self.now = 0.0
        self.runtime = runtime
        self.up = {"A": True, "B": True}
        self.procs = []

    def probe(self, url, timeout):
        cluster = "A" if "master-a" in url else "B"
        if not self.up[cluster]:
            return Observation(ts=self.now, reachable=False, latency_s=timeout)
        return Observation(ts=self.now, reachable=True, latency_s=0.01, alive_workers=2, cores=4, cores_used=4)

    def progress(self, port):
        # every live attempt on an up cluster makes progress every tick
        for p in self.procs:
            if p.port == port and not p.proc.killed:
                return {"completed": int(self.now) if self.world_up(p) else p.frozen,
                        "active_execs": 2, "lost_execs": 0, "seen_execs": 2}
        return None

    def world_up(self, p):
        if not self.up[p.cluster]:
            p.frozen = p.frozen if p.frozen is not None else int(FAULT)
            return False
        return True


class Handle:
    def __init__(self, proc, port, cluster):
        self.proc, self.port, self.cluster, self.frozen = proc, port, cluster, None


CFG = {
    "clusters": {
        "A": {"master_url": "spark://spark-master-a:7077", "ui_url": "http://spark-master-a:8080",
              "master_container": "a", "worker_containers": ["a1"], "expected_workers": 2},
        "B": {"master_url": "spark://spark-master-b:7077", "ui_url": "http://spark-master-b:8080",
              "master_container": "b", "worker_containers": ["b1"], "expected_workers": 2},
    },
    "storage": {"checkpoint_root": "s3a://c", "data_root": "s3a://d", "results_root": "s3a://r"},
    "paths": {},
    "controller": {
        "poll_interval_s": 2.0, "probe_timeout_s": 1.5,
        "health_weights": {"unreachable": 0.45, "workers_lost": 0.25, "latency": 0.10, "stall": 0.15,
                           "executor_loss": 0.05},
        "latency_ewma_alpha": 0.2, "latency_z_low": 3.0, "latency_z_high": 8.0, "stall_limit_s": 120.0,
        "suspect_threshold": 0.95, "failed_threshold": 0.5, "failed_consecutive": 3,
        "recovered_consecutive": 5, "migrate_stall_s": 10.0, "naive_timeout_s": 30.0,
        "placement": {"alpha": 0.4, "beta": 0.5, "gamma": 0.1},
        "reliability_weights": {"availability": 0.4, "recovery": 0.2, "success": 0.2, "health": 0.2},
        "mttr_reference_s": 120.0, "mtbf_prior_s": 900.0, "mtbf_prior_weight": 1.0,
        "max_retries_same_cluster": 1,
    },
    "spark_submit": {"driver_memory": "512m", "executor_memory": "576m", "executor_cores": 1,
                     "total_executor_cores": 4, "ui_port_base": 4040},
}


@pytest.fixture
def setup(tmp_path, monkeypatch):
    world = World()
    handles = []

    def fake_start(self, run, cluster, mtbf_s, now, reason):
        port = self._alloc_port()
        proc = FakeProc(cluster, world, now)
        att = jobs.Attempt(n=len(run.attempts), cluster=cluster, ui_port=port, started=now,
                           log_path="", proc=proc, last_progress_ts=now)
        run.attempts.append(att)
        run.state = jobs.RUNNING
        h = Handle(proc, port, cluster)
        handles.append(h)
        world.procs.append(h)
        self.decisions.log("submit", ts=now, job_id=run.spec.job_id, cluster=cluster, reason=reason)
        return att

    def fake_kill(self, att, reason, now, sig=None):
        att.proc.killed = True
        self._close(att, now, reason)

    monkeypatch.setattr(jobs.JobManager, "start_attempt", fake_start)
    monkeypatch.setattr(jobs.JobManager, "kill_attempt", fake_kill)
    monkeypatch.setattr(jobs, "probe_driver", lambda port, timeout_s=1.0: world.progress(port))
    ctrl = core.Controller(CFG, decisions_file=str(tmp_path / "d.jsonl"),
                           timeseries_file=str(tmp_path / "ts.csv"), logs_dir=str(tmp_path / "logs"),
                           events_dir=str(tmp_path / "ev"), probe=world.probe)
    return world, ctrl


def simulate(world, ctrl, mode, deadline=300.0, outage=True, until=400.0):
    run = ctrl.submit(JobSpec(job_id=f"job-{mode}", script="x.py", mode=mode, deadline_s=deadline,
                              home_cluster="A"), now=0.0)
    while world.now < until and run.state not in jobs.TERMINAL:
        world.now += 2.0
        if outage and world.now >= FAULT:
            world.up["A"] = False
        ctrl.tick(world.now)
    return run


def test_no_fault_all_modes_succeed_on_home_cluster(setup):
    world, ctrl = setup
    run = simulate(world, ctrl, "smart", outage=False)
    assert run.state == jobs.SUCCEEDED and len(run.attempts) == 1


def test_vanilla_job_dies_with_its_cluster(setup):
    world, ctrl = setup
    run = simulate(world, ctrl, "none", deadline=200)
    assert run.state == jobs.FAILED_JOB and "deadline" in run.outcome
    assert [a.cluster for a in run.attempts] == ["A"]


def test_smart_mode_fails_over_quickly(setup):
    world, ctrl = setup
    run = simulate(world, ctrl, "smart")
    assert run.state == jobs.SUCCEEDED
    assert [a.cluster for a in run.attempts] == ["A", "B"]
    failover_ts = run.attempts[1].started
    # 3 polls to FAILED (6 s) + 10 s without progress -> well under the 30 s naive timeout
    assert failover_ts - FAULT <= 16.0


def test_naive_mode_fails_over_after_timeout(setup):
    world, ctrl = setup
    run = simulate(world, ctrl, "naive")
    assert run.state == jobs.SUCCEEDED
    assert [a.cluster for a in run.attempts] == ["A", "B"]
    assert run.attempts[1].started - FAULT >= 30.0


def test_smart_keeps_job_that_still_progresses_when_master_dies(setup, monkeypatch):
    world, ctrl = setup
    # master unreachable, but executors keep finishing tasks
    monkeypatch.setattr(world, "world_up", lambda p: True)
    run = simulate(world, ctrl, "smart", until=50.0)
    assert ctrl.clusters["A"].smart.state == "FAILED"
    assert len(run.attempts) == 1
    assert any(d["kind"] == "keep" for d in ctrl.decisions.recent)


def test_decisions_are_explained(setup):
    world, ctrl = setup
    simulate(world, ctrl, "smart")
    trans = [d for d in ctrl.decisions.recent if d["kind"] == "transition" and d["new"] == "FAILED"
             and d["detector"] == "health"]
    assert trans and "unreachable" in trans[0]["reason"]
    fo = [d for d in ctrl.decisions.recent if d["kind"] == "failover"]
    assert fo and fo[0]["target"] == "B" and "argmin J" in fo[0]["reason"]
    rel = ctrl.snapshot()["clusters"]["A"]["reliability"]
    assert rel["failures"] == 1 and rel["components"]["availability"] < 1.0
