#!/usr/bin/env bash
# Live failover demo (README Step 5), with a timestamp on every line, saved to results/demo/.
#   bash scripts/live_demo.sh [workload] [fault]      e.g.  bash scripts/live_demo.sh etl_taxi cluster_outage
# Watch at the same time: http://localhost:8080 (A), http://localhost:8090 (B), http://localhost:3000 (Grafana)
set -u
WL=${1:-etl_taxi}
FAULT=${2:-cluster_outage}
WAIT_BEFORE_FAULT=${WAIT_BEFORE_FAULT:-40}
mkdir -p results/demo
OUT="results/demo/demo_${WL}_${FAULT}_$(date +%Y%m%d_%H%M%S).txt"
cli() { docker compose exec -T controller python -m controller.cli "$@"; }
log() { while IFS= read -r l; do printf '[%s] %s\n' "$(date +%H:%M:%S)" "$l"; done; }

{
  echo "=== status before ==="; cli status
  echo "=== submit $WL (smart, adaptive) ==="; cli submit "$WL" --mode smart --policy adaptive
  for i in $(seq 1 $((WAIT_BEFORE_FAULT / 5))); do sleep 5; cli status | grep -E "^(cluster|job)"; done
  echo "=== INJECT $FAULT on cluster A ==="; cli chaos "$FAULT" --cluster A
  for i in $(seq 1 60); do
    sleep 5
    s=$(cli status); echo "$s" | grep -E "^(cluster|job)"
    echo "$s" | grep -qE "^job .*: (SUCCEEDED|FAILED)" && break
  done
  echo "=== decision log (explanations) ==="; cli decisions --limit 30
  echo "=== restore cluster A ==="; cli restore
} 2>&1 | log | tee "$OUT"
echo "saved: $OUT"
