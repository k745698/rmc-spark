"""Tiny client for the controller API (handy for live demos / execution videos).

    docker compose exec controller python -m controller.cli status
    docker compose exec controller python -m controller.cli submit etl_taxi --mode smart --policy adaptive
    docker compose exec controller python -m controller.cli chaos cluster_outage --cluster A
    docker compose exec controller python -m controller.cli decisions --limit 20
    docker compose exec controller python -m controller.cli restore
"""
from __future__ import annotations

import argparse
import json

import requests

API = "http://localhost:8000"


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    s = sub.add_parser("submit")
    s.add_argument("workload")
    s.add_argument("--mode", default="smart", choices=["none", "naive", "smart"])
    s.add_argument("--policy", default="adaptive", choices=["never", "always", "adaptive", "young"])
    c = sub.add_parser("chaos")
    c.add_argument("fault")
    c.add_argument("--cluster", default="A")
    c.add_argument("--duration", type=float, default=None)
    d = sub.add_parser("decisions")
    d.add_argument("--limit", type=int, default=20)
    sub.add_parser("restore")
    a = p.parse_args()

    if a.cmd == "status":
        out = {"clusters": requests.get(f"{API}/clusters").json(), "jobs": requests.get(f"{API}/jobs").json()}
        for name, cl in out["clusters"].items():
            h = cl["health"]
            print(f"cluster {name}: {cl['state_smart']:8s} H={h if h is None else round(h, 2)} "
                  f"workers={cl['alive_workers']} R={cl['reliability']['R']:.2f} causes={cl['top_causes']}")
        for jid, j in out["jobs"].items():
            print(f"job {jid}: {j['state']} on {j['cluster']} attempts={j['attempts']} failovers={j['failovers']}")
        return
    if a.cmd == "submit":
        r = requests.post(f"{API}/jobs", json={"workload": a.workload, "mode": a.mode, "policy": a.policy})
    elif a.cmd == "chaos":
        r = requests.post(f"{API}/chaos", json={"fault": a.fault, "cluster": a.cluster, "duration_s": a.duration})
    elif a.cmd == "restore":
        r = requests.post(f"{API}/chaos/restore")
    else:
        r = requests.get(f"{API}/decisions", params={"limit": a.limit})
    print(json.dumps(r.json(), indent=2, default=str))


if __name__ == "__main__":
    main()
