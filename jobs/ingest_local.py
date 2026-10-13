"""Copy downloaded datasets from ./datasets (bind-mounted at /workspace on every container) into MinIO."""
from __future__ import annotations

import argparse
import os

from jobs.common import spark_session


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--local", default="/workspace/datasets")
    p.add_argument("--data-root", default="s3a://data")
    a = p.parse_args()
    spark = spark_session("rmc-ingest")

    tlc = os.path.join(a.local, "tlc")
    if os.path.isdir(tlc) and os.listdir(tlc):
        df = spark.read.parquet(f"file://{tlc}")
        df.write.mode("overwrite").parquet(f"{a.data_root}/tlc")
        print("tlc rows:", df.count())
    for name in ("ai4i2020.csv", "creditcard.csv"):
        path = os.path.join(a.local, "case", name)
        if os.path.exists(path):
            df = spark.read.option("header", True).csv(f"file://{path}")
            df.coalesce(1).write.mode("overwrite").option("header", True).csv(f"{a.data_root}/case/{name}")
            print(name, "rows:", df.count())
    spark.stop()


if __name__ == "__main__":
    main()
