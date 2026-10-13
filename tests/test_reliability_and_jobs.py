import pytest

from controller.jobs import on_attempt_exit, while_running
from controller.reliability import ClusterReliability, system_mtbf
from controller.statemachine import FAILED, HEALTHY, SUSPECT

RW = {"availability": 0.4, "recovery": 0.2, "success": 0.2, "health": 0.2}


def test_reliability_tracks_up_down_and_mttr():
    r = ClusterReliability("A", mtbf_prior_s=900, prior_weight=1, start_ts=0)
    r.observe(100, failed=False, health=1.0)
    r.observe(110, failed=True, health=0.0)     # failure starts at t=110
    r.observe(140, failed=True, health=0.0)
    r.observe(150, failed=False, health=1.0)    # repaired after 40 s
    assert r.failures == 1
    assert r.uptime == pytest.approx(110)
    assert r.downtime == pytest.approx(40)
    assert r.mttr == pytest.approx(40)
    assert r.availability == pytest.approx(110 / 150)
    assert r.mtbf == pytest.approx((900 + 110) / 2)


def test_reliability_score_contributions_sum_to_r():
    r = ClusterReliability("A", 900, 1, 0)
    r.observe(10, False, 0.9)
    r.record_job(True)
    r.record_job(False)
    s = r.score(RW, mttr_ref_s=120)
    assert s["R"] == pytest.approx(sum(s["contributions"].values()))
    assert s["components"]["success"] == 0.5
    assert 0 <= s["R"] <= 1


def test_system_mtbf_pools_clusters():
    a = ClusterReliability("A", 600, 1, 0)
    b = ClusterReliability("B", 600, 1, 0)
    a.observe(300, False, 1)
    b.observe(300, False, 1)
    assert system_mtbf([a, b]) == pytest.approx((600 + 600) / 1)
    a.observe(301, True, 0)
    assert system_mtbf([a, b]) == pytest.approx((600 + 601) / 2)


@pytest.mark.parametrize("mode,code,state,retries,expected", [
    ("none", 0, HEALTHY, 0, "succeed"),
    ("none", 1, FAILED, 0, "fail"),
    ("naive", 1, HEALTHY, 0, "failover"),
    ("smart", 1, HEALTHY, 0, "retry"),
    ("smart", 1, HEALTHY, 1, "failover"),
    ("smart", 1, SUSPECT, 0, "failover"),
    ("smart", -9, FAILED, 0, "failover"),
])
def test_on_attempt_exit(mode, code, state, retries, expected):
    assert on_attempt_exit(mode, code, state, retries, max_retries=1) == expected


@pytest.mark.parametrize("mode,state,stall,expected", [
    ("none", FAILED, 999, "continue"),
    ("naive", FAILED, 0, "migrate"),
    ("smart", FAILED, 2, "keep"),          # dead master but executors still progressing
    ("smart", FAILED, 15, "migrate"),
    ("smart", SUSPECT, 999, "continue"),
    ("smart", HEALTHY, 999, "continue"),
])
def test_while_running(mode, state, stall, expected):
    assert while_running(mode, state, stall, migrate_stall_s=10) == expected
