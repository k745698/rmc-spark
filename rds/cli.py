"""Common command-line context passed by the controller to every job (spark-submit args)."""
from __future__ import annotations

import argparse
import os
from dataclasses import dataclass


@dataclass
class JobContext:
    job_id: str
    attempt: int
    cluster: str
    policy: str
    mtbf_s: float
    checkpoint_root: str
    data_root: str
    results_root: str
    events_dir: str

    @property
    def events_file(self) -> str | None:
        return os.path.join(self.events_dir, f"{self.job_id}.jsonl") if self.events_dir else None


def base_parser(description: str = "") -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=description)
    p.add_argument("--job-id", required=True)
    p.add_argument("--attempt", type=int, default=0)
    p.add_argument("--cluster", default="?")
    p.add_argument("--policy", default="never", choices=["never", "always", "adaptive", "daly", "young"])
    p.add_argument("--mtbf", type=float, default=900.0, help="MTBF estimate (s) from the controller")
    p.add_argument("--checkpoint-root", default="s3a://checkpoints")
    p.add_argument("--data-root", default="s3a://data")
    p.add_argument("--results-root", default="s3a://results")
    p.add_argument("--events-dir", default="/workspace/results/events")
    return p


def context_from_args(args) -> JobContext:
    return JobContext(job_id=args.job_id, attempt=args.attempt, cluster=args.cluster,
                      policy=args.policy, mtbf_s=args.mtbf, checkpoint_root=args.checkpoint_root,
                      data_root=args.data_root, results_root=args.results_root,
                      events_dir=args.events_dir)
