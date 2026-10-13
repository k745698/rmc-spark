"""Load configs/clusters.yaml."""
from __future__ import annotations

import os

import yaml


def load_config(path: str | None = None) -> dict:
    path = path or os.environ.get("RMC_CONFIG", "configs/clusters.yaml")
    with open(path, encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)
    for key in ("clusters", "storage", "paths", "controller", "spark_submit"):
        if key not in cfg:
            raise ValueError(f"config {path} is missing section '{key}'")
    return cfg
