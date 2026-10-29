### Table 11 Experimental Results Summary

| system | fault | runs | success_rate | median_duration_s | median_downtime_s | median_detection_s | median_failover_s | mean_recomputed_s | mean_checkpoint_s | mean_availability |
|---|---|---|---|---|---|---|---|---|---|---|
| B1_vanilla | cluster_outage | 2 | 0 | 717 | 616 | 8.05 |  | 0 | 0 | 0.14 |
| B2_fixed_ckpt | cluster_outage | 3 | 0 | 718 | 620 | 7.22 |  | 0 | 18 | 0.137 |
| B3_naive_ha | cluster_outage | 1 | 1 | 240 | 134 | 30.7 | 30.7 | 62.2 | 0 | 0.443 |
| P_rmc | cluster_outage | 2 | 1 | 214 | 122 | 7.63 | 9.22 | 55.7 | 0 | 0.432 |
| B1_vanilla | executor_kill | 1 | 1 | 160 | 68.1 |  |  | 0 | 0 | 0.575 |
| B2_fixed_ckpt | executor_kill | 3 | 1 | 148 | 34 |  |  | 0 | 37.3 | 0.785 |
| B3_naive_ha | executor_kill | 1 | 1 | 152 | 46.1 |  |  | 0 | 0 | 0.697 |
| P_rmc | executor_kill | 3 | 1 | 140 | 48 |  |  | 0 | 0 | 0.654 |
| B1_vanilla | none | 3 | 1 | 92.1 | 0 |  |  | 0 | 0 | 1 |
| B2_fixed_ckpt | none | 3 | 1 | 114 | 0 |  |  | 0 | 32.5 | 1 |
| B3_naive_ha | none | 3 | 1 | 106 | 0 |  |  | 0 | 0 | 1 |
| P_rmc | none | 3 | 1 | 92.1 | 0 |  |  | 0 | 0 | 1 |
