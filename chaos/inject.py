"""Fault injection for the testbed (chaos-engineering style), via the Docker Engine API.

Faults (Section 2 / Fig. 3 of the paper):
  executor_kill     SIGKILL the executor JVMs on one worker of the cluster (Spark recomputes)
  worker_kill       kill one worker container (stays down until restore)
  master_kill       kill the master container (running executors keep working)
  cluster_outage    kill master + all workers of the cluster
  network_partition disconnect every container of the cluster from the network
  network_delay     tc netem delay on every container of the cluster (gray failure)
  straggler         throttle one worker to 0.25 CPU (gray failure)
  disk_full         fill the Spark local-dir tmpfs of one worker
  driver_crash      SIGKILL the job's driver process (needs the controller + job id)

CLI:  python -m chaos.inject cluster_outage --cluster A
      python -m chaos.inject restore
"""
from __future__ import annotations

import argparse
import threading
import time

import docker
from docker.errors import APIError, NotFound

NETWORK = "rmc-net"
FAULTS = ("executor_kill", "worker_kill", "master_kill", "cluster_outage", "network_partition",
          "network_delay", "straggler", "disk_full", "driver_crash")
TRANSIENT = ("network_partition", "network_delay", "straggler", "disk_full")   # auto-restored after duration


class FaultInjector:
    def __init__(self, cfg: dict, client=None):
        self.cfg = cfg
        self.client = client or docker.from_env()

    # ------------------------------------------------------------------ helpers
    def _containers(self, cluster: str, role: str = "all") -> list:
        c = self.cfg["clusters"][cluster]
        names = []
        if role in ("all", "master"):
            names.append(c["master_container"])
        if role in ("all", "worker"):
            names += list(c["worker_containers"])
        return names

    def _get(self, name: str):
        return self.client.containers.get(name)

    def _exec(self, name: str, cmd: str) -> str:
        res = self._get(name).exec_run(["sh", "-c", cmd])
        return res.output.decode(errors="replace") if res.output else ""

    def _hostname(self, name: str) -> str:
        return self._get(name).attrs["Config"]["Hostname"]

    # ------------------------------------------------------------------ inject
    def inject(self, fault: str, cluster: str, duration_s: float | None = None,
               controller=None, job_id: str | None = None) -> dict:
        if fault not in FAULTS:
            raise ValueError(f"unknown fault {fault}; choose from {FAULTS}")
        if cluster not in self.cfg["clusters"]:
            raise ValueError(f"unknown cluster {cluster}")
        worker = self._containers(cluster, "worker")[0]
        info = {"fault": fault, "cluster": cluster, "ts": time.time()}

        if fault == "executor_kill":
            info["output"] = self._exec(worker, "pkill -9 -f CoarseGrainedExecutorBackend; echo done")
            info["target"] = worker
        elif fault == "worker_kill":
            self._get(worker).kill()
            info["target"] = worker
        elif fault == "master_kill":
            name = self._containers(cluster, "master")[0]
            self._get(name).kill()
            info["target"] = name
        elif fault == "cluster_outage":
            for name in self._containers(cluster):
                self._get(name).kill()
            info["target"] = self._containers(cluster)
        elif fault == "network_partition":
            net = self.client.networks.get(NETWORK)
            for name in self._containers(cluster):
                net.disconnect(name, force=True)
            info["target"] = self._containers(cluster)
        elif fault == "network_delay":
            for name in self._containers(cluster):
                self._exec(name, "tc qdisc replace dev eth0 root netem delay 300ms 50ms")
            info["target"] = self._containers(cluster)
        elif fault == "straggler":
            self._get(worker).update(cpu_period=100000, cpu_quota=25000)
            info["target"] = worker
        elif fault == "disk_full":
            info["output"] = self._exec(
                worker, "avail=$(df --output=avail -k /tmp/spark-local | tail -1); "
                        "fallocate -l $(( (avail - 1024) * 1024 )) /tmp/spark-local/rmc_fill; df -h /tmp/spark-local")
            info["target"] = worker
        elif fault == "driver_crash":
            if controller is None or job_id is None:
                raise ValueError("driver_crash needs the controller and a job id")
            info["crashed"] = controller.jobs.crash_driver(job_id)
            info["target"] = job_id

        if fault in TRANSIENT and duration_s:
            t = threading.Timer(duration_s, self.restore_cluster, args=(cluster,))
            t.daemon = True
            t.start()
            info["auto_restore_after_s"] = duration_s
        return info

    # ------------------------------------------------------------------ restore
    def restore_cluster(self, cluster: str) -> None:
        names = self._containers(cluster)
        net = self.client.networks.get(NETWORK)
        # 1) containers up: master first, so workers can register
        for name in names:
            try:
                ctr = self._get(name)
                if ctr.status != "running":
                    ctr.start()
                    if name == names[0]:
                        time.sleep(3)
            except (NotFound, APIError):
                pass
        # 2) network attached (with the hostname alias other containers resolve)
        for name in names:
            try:
                ctr = self._get(name)
                ctr.reload()
                if NETWORK not in ctr.attrs["NetworkSettings"]["Networks"]:
                    net.connect(name, aliases=[self._hostname(name)])
            except (NotFound, APIError):
                pass
        # 3) gray-failure knobs back to normal
        for name in names:
            try:
                self._exec(name, "tc qdisc del dev eth0 root 2>/dev/null; rm -f /tmp/spark-local/rmc_fill")
                if name != names[0]:
                    self._get(name).update(cpu_period=100000, cpu_quota=200000)
            except (NotFound, APIError):
                pass

    def restore_all(self) -> None:
        for cluster in self.cfg["clusters"]:
            self.restore_cluster(cluster)


def main():
    from controller.config import load_config
    p = argparse.ArgumentParser(description="RMC-Spark fault injector")
    p.add_argument("fault", choices=FAULTS + ("restore",))
    p.add_argument("--cluster", default="A")
    p.add_argument("--duration", type=float, default=None, help="auto-restore after N s (transient faults)")
    p.add_argument("--config", default=None)
    a = p.parse_args()
    inj = FaultInjector(load_config(a.config))
    if a.fault == "restore":
        inj.restore_all()
        print("all clusters restored")
        return
    print(inj.inject(a.fault, a.cluster, duration_s=a.duration))
    if a.duration and a.fault in TRANSIENT:
        time.sleep(a.duration + 1)   # keep the process alive for the auto-restore timer


if __name__ == "__main__":
    main()
