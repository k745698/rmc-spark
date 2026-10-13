"""REST API + Prometheus exporter around the controller (service `controller` in docker-compose).

  GET  /clusters      health, state, top causes and reliability score per cluster
  GET  /jobs          job states
  POST /jobs          submit a job   {"workload": "etl_taxi", "mode": "smart", "policy": "adaptive"}
  GET  /decisions     last N explainable decisions
  POST /chaos         inject a fault {"fault": "cluster_outage", "cluster": "A"}
  POST /chaos/restore restore every cluster
  GET  /metrics       Prometheus metrics (scraped by Prometheus, shown in Grafana)
"""
from __future__ import annotations

import threading
import time
import uuid

from fastapi import FastAPI, HTTPException
from prometheus_client import Gauge, make_asgi_app
from pydantic import BaseModel

from .config import load_config
from .core import Controller
from .jobs import JobSpec
from .statemachine import STATE_CODE
from .workloads import WORKLOADS

cfg = load_config()
controller = Controller(cfg)
_stop = threading.Event()

G_HEALTH = Gauge("rmc_cluster_health", "Health score H_k", ["cluster"])
G_STATE = Gauge("rmc_cluster_state", "0 healthy, 1 suspect, 2 failed (health detector)", ["cluster"])
G_WORKERS = Gauge("rmc_cluster_alive_workers", "Alive workers reported by the master", ["cluster"])
G_UTIL = Gauge("rmc_cluster_utilisation", "cores used / cores", ["cluster"])
G_REL = Gauge("rmc_cluster_reliability", "Reliability score R_k", ["cluster"])
G_FAILOVERS = Gauge("rmc_failovers_total", "Failovers performed by the controller")
G_RUNNING = Gauge("rmc_jobs_running", "Jobs currently running")
G_MTBF = Gauge("rmc_mtbf_seconds", "Pooled MTBF estimate used by the adaptive checkpoint policy")


def _export(ctrl: Controller) -> None:
    snap = ctrl.snapshot()
    for name, c in snap["clusters"].items():
        if c["health"] is not None:
            G_HEALTH.labels(name).set(c["health"])
        G_STATE.labels(name).set(STATE_CODE[c["state_smart"]])
        G_WORKERS.labels(name).set(c["alive_workers"] or 0)
        G_UTIL.labels(name).set((c["cores_used"] or 0) / c["cores"] if c["cores"] else 0)
        G_REL.labels(name).set(c["reliability"]["R"])
    G_FAILOVERS.set(snap["failovers_total"])
    G_RUNNING.set(sum(1 for j in snap["jobs"].values() if j["state"] == "RUNNING"))
    G_MTBF.set(snap["mtbf_s"])


controller.listeners.append(_export)
app = FastAPI(title="RMC-Spark controller")
app.mount("/metrics", make_asgi_app())


@app.on_event("startup")
def _start_loop():
    threading.Thread(target=controller.run_forever, args=(_stop,), daemon=True).start()


@app.on_event("shutdown")
def _stop_loop():
    _stop.set()


class SubmitRequest(BaseModel):
    workload: str
    mode: str = "smart"
    policy: str = "adaptive"
    job_id: str | None = None
    deadline_s: float = 1800.0


class ChaosRequest(BaseModel):
    fault: str
    cluster: str = "A"
    duration_s: float | None = None


@app.get("/clusters")
def clusters():
    return controller.snapshot()["clusters"]


@app.get("/jobs")
def jobs():
    return controller.snapshot()["jobs"]


@app.post("/jobs")
def submit(req: SubmitRequest):
    if req.workload not in WORKLOADS:
        raise HTTPException(400, f"unknown workload, choose from {sorted(WORKLOADS)}")
    w = WORKLOADS[req.workload]
    spec = JobSpec(job_id=req.job_id or f"{req.workload}-{uuid.uuid4().hex[:8]}", script=w["script"],
                   args=w.get("args", []), policy=req.policy, mode=req.mode, deadline_s=req.deadline_s,
                   extra_conf=w.get("conf", {}))
    run = controller.submit(spec)
    return {"job_id": spec.job_id, "state": run.state}


@app.get("/decisions")
def decisions(limit: int = 50):
    return controller.decisions.recent[-limit:]


@app.post("/chaos")
def chaos(req: ChaosRequest):
    from chaos.inject import FaultInjector
    inj = FaultInjector(cfg)
    try:
        info = inj.inject(req.fault, req.cluster, duration_s=req.duration_s, controller=controller)
    except ValueError as e:
        raise HTTPException(400, str(e))
    controller.decisions.log("fault_injected", fault=req.fault, cluster=req.cluster, info=info)
    return {"injected": req.fault, "cluster": req.cluster, "at": time.time(), "info": info}


@app.post("/chaos/restore")
def restore():
    from chaos.inject import FaultInjector
    FaultInjector(cfg).restore_all()
    return {"restored": True}
