"""Workload catalogue shared by the API and the experiment runner."""

WORKLOADS = {
    "etl_taxi": {"script": "jobs/etl_taxi.py", "args": ["--source", "synthetic"]},
    "ml_taxi": {"script": "jobs/ml_pipeline.py", "args": ["--dataset", "taxi"]},
    "iterative_rank": {"script": "jobs/iterative_rank.py", "args": ["--iterations", "12"]},
    "streaming": {"script": "jobs/streaming_rate.py", "args": ["--target-batches", "120"]},
    # industry case studies (Section 18) - need `python scripts/download_data.py --case-studies`
    "case_maintenance": {"script": "jobs/ml_pipeline.py", "args": ["--dataset", "ai4i"]},
    "case_fraud": {"script": "jobs/ml_pipeline.py", "args": ["--dataset", "creditcard"]},
}
