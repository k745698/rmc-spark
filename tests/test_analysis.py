import pytest

from analysis.metrics import (availability, checkpoint_time, recomputed_work, steady_state_availability,
                              stream_recovery, utilisation)
from analysis.stats import bootstrap_ci, cliffs_delta, magnitude


def test_recomputed_work_counts_repeated_stages_only():
    evs = [
        {"event": "stage_completed", "stage": "clean", "compute_s": 10, "attempt": 0},
        {"event": "stage_completed", "stage": "enrich", "compute_s": 20, "attempt": 0},
        {"event": "stage_completed", "stage": "clean", "compute_s": 11, "attempt": 1},   # redone
        {"event": "stage_restored", "stage": "enrich", "attempt": 1},
        {"event": "stage_completed", "stage": "agg", "compute_s": 5, "attempt": 1},
    ]
    assert recomputed_work(evs) == 11


def test_checkpoint_time():
    evs = [{"event": "stage_completed", "checkpoint": True, "write_s": 2.5},
           {"event": "stage_completed", "checkpoint": False},
           {"event": "stage_completed", "checkpoint": True, "write_s": 1.5}]
    assert checkpoint_time(evs) == (4.0, 2)


def test_stream_recovery():
    evs = [{"event": "batch_progress", "ts": t, "processed_rps": 1000.0} for t in range(0, 60, 2)]
    evs += [{"event": "batch_progress", "ts": t, "processed_rps": 100.0} for t in range(60, 80, 2)]
    evs += [{"event": "batch_progress", "ts": t, "processed_rps": 950.0} for t in range(80, 140, 2)]
    assert stream_recovery(evs, t_fault=60.0) == pytest.approx(20.0)
    assert stream_recovery(evs, t_fault=60.0, hold_s=1000) is None


def test_utilisation():
    rows = [{"ts": 0, "cluster": "A", "cores": 4, "cores_used": 4},
            {"ts": 10, "cluster": "A", "cores": 4, "cores_used": 0},
            {"ts": 20, "cluster": "A", "cores": 4, "cores_used": 0}]
    assert utilisation(rows) == pytest.approx(0.5)


def test_availability():
    assert availability(100, 25) == 0.75
    assert steady_state_availability(900, 100) == 0.9


def test_cliffs_delta_and_magnitude():
    assert cliffs_delta([1, 2, 3], [10, 11, 12]) == -1.0
    assert cliffs_delta([5, 5], [5, 5]) == 0.0
    assert magnitude(-0.9) == "large" and magnitude(0.1) == "negligible"


def test_bootstrap_ci_contains_mean():
    m, lo, hi = bootstrap_ci([1.0, 2.0, 3.0, 4.0, 5.0])
    assert lo <= m <= hi and m == 3.0
    assert bootstrap_ci([]) == (None, None, None)
