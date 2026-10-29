#!/usr/bin/env bash
# macOS/Linux version of run_minimum.ps1 — minimum experiment (~1.5-2 h) end to end.
#   bash scripts/run_minimum.sh              # full run
#   bash scripts/run_minimum.sh --skip-data  # data already generated
#   bash scripts/run_minimum.sh --fresh      # delete old results/raw/minimum first
set -euo pipefail
cd "$(dirname "$0")/.."

SKIP_DATA=0; FRESH=0
for a in "$@"; do
  case "$a" in
    --skip-data) SKIP_DATA=1 ;;
    --fresh) FRESH=1 ;;
    *) echo "unknown option: $a"; exit 1 ;;
  esac
done

step() { printf '\n\033[36m=== %s (%s) ===\033[0m\n' "$1" "$(date +%H:%M:%S)"; }
ex()   { docker compose exec -T controller bash -c "set -o pipefail; $1"; }
start=$(date +%s)

step "1/5 starting the testbed"
docker compose up -d
for i in $(seq 1 60); do
  n=$(docker compose exec -T controller python -m controller.cli status 2>/dev/null | grep -c HEALTHY || true)
  [ "$n" -ge 2 ] && break
  [ "$i" -eq 60 ] && { echo "clusters did not become HEALTHY - check http://localhost:8080 and :8090"; exit 1; }
  sleep 5
done
docker compose exec -T controller python -m controller.cli status

[ "$FRESH" -eq 1 ] && rm -rf results/raw/minimum

if [ "$SKIP_DATA" -eq 0 ]; then
  step "2/5 generating smaller datasets (1.5 M trips, 1 M edges)"
  ex "spark-submit --master spark://spark-master-a:7077 --conf spark.driver.host=controller --total-executor-cores 4 --executor-memory 576m jobs/datagen.py --taxi-rows 1500000 --graph-nodes 100000 --graph-edges 1000000"
fi

step "3/5 calibrating fault time and deadline from clean runs"
ex "python -m experiments.calibrate experiments/configs/minimum.yaml --runs 2"

step "4/5 running the 36-run experiment (about 1.5 h)"
ex "python -m experiments.run_matrix experiments/configs/minimum.yaml 2>&1 | tee -a results/raw/minimum_console.txt"

step "5/5 producing tables and figures"
ex "python -m analysis.report results/raw/minimum --out results/report"

printf '\n\033[32mDONE in %s min. Results: results/raw/minimum/runs.csv and results/report/\033[0m\n' $(( ($(date +%s) - start) / 60 ))
