"""Download the public datasets into ./datasets (run inside the controller container or on the host).

    python scripts/download_data.py --tlc-months 2024-01           # NYC TLC yellow taxi (~50 MB/month)
    python scripts/download_data.py --case-studies                 # AI4I 2020 (~0.5 MB) + credit-card (~150 MB)

Then copy them into MinIO with:
    spark-submit --master spark://spark-master-a:7077 jobs/ingest_local.py
"""
from __future__ import annotations

import argparse
import os
import urllib.request
import zipfile

TLC_URL = "https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_{month}.parquet"
AI4I_URL = "https://archive.ics.uci.edu/static/public/601/ai4i+2020+predictive+maintenance+dataset.zip"
CREDIT_URL = "https://storage.googleapis.com/download.tensorflow.org/data/creditcard.csv"


def fetch(url: str, dest: str) -> None:
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        print(f"exists: {dest}")
        return
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    print(f"downloading {url}")
    tmp = dest + ".part"
    urllib.request.urlretrieve(url, tmp)
    os.replace(tmp, dest)
    print(f"  -> {dest} ({os.path.getsize(dest) / 1e6:.1f} MB)")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="datasets")
    p.add_argument("--tlc-months", nargs="*", default=[], help="e.g. 2024-01 2024-02")
    p.add_argument("--case-studies", action="store_true")
    a = p.parse_args()

    for m in a.tlc_months:
        fetch(TLC_URL.format(month=m), os.path.join(a.out, "tlc", f"yellow_tripdata_{m}.parquet"))
    if a.case_studies:
        z = os.path.join(a.out, "case", "ai4i.zip")
        fetch(AI4I_URL, z)
        with zipfile.ZipFile(z) as zf:
            for name in zf.namelist():
                if name.lower().endswith(".csv"):
                    with zf.open(name) as src, open(os.path.join(a.out, "case", "ai4i2020.csv"), "wb") as dst:
                        dst.write(src.read())
        fetch(CREDIT_URL, os.path.join(a.out, "case", "creditcard.csv"))


if __name__ == "__main__":
    main()
