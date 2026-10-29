### Table 12 Comparative Benchmark Analysis

| system | fault_runs | success_rate | availability_mean | availability_ci_low | availability_ci_high | median_downtime_s | mean_recomputed_s | clean_overhead_vs_B1 | p_downtime_vs_B1 | cliffs_delta_vs_B1 | effect |
|---|---|---|---|---|---|---|---|---|---|---|---|
| B1_vanilla | 3 | 0.333 | 0.285 | 0.138 | 0.575 | 614 | 0 | 0 |  |  |  |
| B2_fixed_ckpt | 6 | 0.5 | 0.461 | 0.227 | 0.717 | 336 | 0 | 0.239 | 0.905 | -0.111 | negligible |
| B3_naive_ha | 2 | 1 | 0.57 | 0.443 | 0.697 | 89.8 | 31.1 | 0.152 | 0.4 | -0.667 | large |
| P_rmc | 5 | 1 | 0.565 | 0.469 | 0.657 | 52 | 22.3 | -0.000239 | 0.143 | -0.733 | large |
