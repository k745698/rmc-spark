# Screenshots to take for the paper / viva

Charts for Figs. 21–24 are **generated** (600 DPI, `results/report/`), so do not screenshot those.
Screenshots are evidence that the system really ran. Use **Win + Shift + S** (a window or region),
browser zoom 100–110 %, light theme, and crop the browser chrome. Save them in `paper/Screenshots/` with the names below.

| # | When | What to open | What must be visible | File name | Supports |
|---|---|---|---|---|---|
| S1 | after `docker compose up -d` | terminal: `docker compose ps` | all 10 services `running`, `rmc-minio-init` `exited (0)` | `S01 testbed containers.png` | §13 Experimental setup / Fig. 19 |
| S2 | testbed idle | <http://localhost:8080> and <http://localhost:8090> side by side | "Alive Workers: 2", "Cores in use: 4 Total" on **both** masters | `S02 spark masters A and B.png` | §5 Architecture, §13 |
| S3 | testbed idle | <http://localhost:9001> (rmcadmin / rmcadmin123) → Buckets | buckets `data`, `checkpoints`, `results` | `S03 minio buckets.png` | §6 Data engineering |
| S4 | testbed idle | <http://localhost:9090/targets> | all targets **UP** | `S04 prometheus targets.png` | §8 Monitoring (Fig. 11) |
| S5 | job running (~20 s after submit) | <http://localhost:4040> → **Jobs**, then a job → **DAG Visualization** | stage DAG of `etl_taxi` | `S05 spark DAG etl_taxi.png` | §7 Spark execution (Fig. 10) |
| S6 | job running on A | <http://localhost:8080> | "Running Applications: 1" on A, B idle | `S06 job running on A.png` | §10 Coordination |
| **S7** | **~10–20 s after the cluster_outage** | Grafana <http://localhost:3000> → RMC-Spark → Resilience Overview (time range "Last 15 minutes", refresh 5 s) | **H_A dropping to ~0**, state FAILED, B's running jobs rising | `S07 grafana failover.png` | §8, §9, Fig. 23 (the key screenshot) |
| S8 | right after the failover | <http://localhost:8090> | the job now listed as running on **B** | `S08 job resumed on B.png` | §9 Recovery |
| **S9** | job finished | terminal: output of `controller.cli decisions` (or `results/demo/demo_*.txt`) | `transition SUSPECT→FAILED` with reason, `failover ... argmin J -> B`, `job_end SUCCEEDED` | `S09 decision log.png` | §11 Explainability (Table 7) |
| S10 | job finished | terminal: `type results\events\<job_id>.jsonl` (or the MinIO `checkpoints/<job_id>/` folder) | `stage_restored` events on attempt 1 / `_RDS_COMMIT` markers | `S10 stage restore evidence.png` | §9 resume from committed stages |
| S11 | after `controller.cli status` | terminal | per-cluster `R=` reliability score and `causes=` | `S11 reliability scores.png` | §11 Eq. 10 |
| S12 | smoke/full matrix running | terminal with the `run_matrix` output (`[k/N] ... -> SUCCEEDED ... clusters=A>B`) | a B1 run FAILED at the deadline and a P run SUCCEEDED on `A>B` | `S12 experiment runner.png` | §13, §15 |
| S13 | after `pytest` | terminal | `56 passed` | `S13 tests passing.png` | Status / verification paragraph |
| S14 (optional) | <http://localhost:8000/docs> | Swagger page of the controller API | `S14 controller api.png` | §5 |

**Timing tip for S7/S8.** Run `bash scripts/live_demo.sh` and keep Grafana + both Spark UIs open. The fault fires about
40 s after the submit, the cluster turns FAILED about 6 s later, and the failover follows about 10 s after that. Take
S7 then and S8 a few seconds later.

**Video (README §11).** If you record with OBS: the same windows, one clip for `live_demo.sh` end to end.
