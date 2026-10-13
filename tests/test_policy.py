import math

import pytest

from rds.events import EventLog, read_events
from rds.policy import (AdaptivePolicy, AlwaysPolicy, Ewma, NeverPolicy, daly_interval, expected_lost_work,
                        make_policy, young_interval)


def test_young_interval_matches_formula():
    assert young_interval(2.0, 900.0) == pytest.approx(math.sqrt(2 * 2 * 900))


def test_daly_close_to_young_when_cost_small():
    c, m = 1.0, 10_000.0
    assert daly_interval(c, m) == pytest.approx(young_interval(c, m), rel=0.02)


def test_daly_returns_mtbf_when_cost_large():
    assert daly_interval(500.0, 100.0) == 100.0


def test_interval_grows_with_mtbf():
    assert daly_interval(3.0, 3600) > daly_interval(3.0, 600) > daly_interval(3.0, 60)


def test_invalid_inputs_rejected():
    with pytest.raises(ValueError):
        young_interval(0, 10)
    with pytest.raises(ValueError):
        daly_interval(1, -5)


def test_expected_lost_work():
    assert expected_lost_work(60.0, 4.0) == 34.0


def test_never_and_always():
    assert not NeverPolicy().decide(1e6, 1.0).checkpoint
    assert NeverPolicy().decide(0, 1.0, force=True).checkpoint
    assert AlwaysPolicy().decide(0.0, 99.0).checkpoint


def test_adaptive_checkpoints_once_work_reaches_tau():
    pol = AdaptivePolicy(mtbf_s=900.0)
    tau = pol.interval(3.0)
    assert not pol.decide(tau * 0.5, 3.0).checkpoint
    d = pol.decide(tau * 1.01, 3.0)
    assert d.checkpoint and d.interval_s == pytest.approx(tau)


def test_adaptive_checkpoints_more_often_when_failures_frequent():
    work, cost = 40.0, 3.0
    assert not AdaptivePolicy(mtbf_s=3600).decide(work, cost).checkpoint
    assert AdaptivePolicy(mtbf_s=120).decide(work, cost).checkpoint


def test_make_policy():
    assert make_policy("never").name == "never"
    assert make_policy("always").name == "always"
    assert make_policy("adaptive", 100).mtbf_s == 100
    assert make_policy("young").formula == "young"
    with pytest.raises(ValueError):
        make_policy("sometimes")


def test_ewma():
    e = Ewma(prior=10.0, alpha=0.5)
    assert e.value == 10.0
    e.update(2.0)
    assert e.value == 2.0          # first observation replaces the prior
    e.update(4.0)
    assert e.value == 3.0


def test_event_log_roundtrip(tmp_path):
    path = tmp_path / "ev" / "job.jsonl"
    log = EventLog(str(path), job_id="j1", attempt=0)
    log.emit("stage_completed", stage="clean", compute_s=1.5)
    with open(path, "a") as fh:
        fh.write('{"truncated": ')       # simulate a driver killed mid-write
    evs = read_events(str(path))
    assert len(evs) == 1 and evs[0]["stage"] == "clean" and evs[0]["job_id"] == "j1"
