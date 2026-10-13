import pytest

from controller.anomaly import EwmaZScore, ramp
from controller.health import HealthModel, Observation
from controller.orchestrator import ClusterView, place
from controller.statemachine import FAILED, HEALTHY, SUSPECT, HealthStateMachine, TimeoutDetector

W = {"unreachable": 0.45, "workers_lost": 0.25, "latency": 0.10, "stall": 0.15, "executor_loss": 0.05}


def obs(**kw):
    base = dict(ts=0.0, reachable=True, latency_s=0.01, alive_workers=2, cores=4, cores_used=0)
    base.update(kw)
    return Observation(**base)


def test_ramp():
    assert ramp(1, 3, 8) == 0 and ramp(8, 3, 8) == 1 and ramp(5.5, 3, 8) == pytest.approx(0.5)


def test_ewma_z_detects_latency_jump_and_does_not_learn_outliers():
    z = EwmaZScore(alpha=0.2, warmup=5)
    for _ in range(30):
        z.update(0.010)
    mean_before = z.mean
    assert z.update(0.400, z_gate=3.0) > 8
    assert z.mean == mean_before


def test_healthy_cluster_scores_one():
    hm = HealthModel(W, expected_workers=2)
    assert hm.assess(obs()).health == pytest.approx(1.0)


def test_unreachable_master_is_below_failed_threshold():
    rep = HealthModel(W, expected_workers=2).assess(obs(reachable=False))
    assert rep.health < 0.5
    assert rep.top_causes()[0][0] == "unreachable"


def test_one_lost_worker_stays_healthy():
    rep = HealthModel(W, expected_workers=2).assess(obs(alive_workers=1))
    assert rep.health > 0.85


def test_zero_workers_is_critical():
    rep = HealthModel(W, expected_workers=2).assess(obs(alive_workers=0))
    assert rep.health == 0.0 and rep.critical and rep.top_causes()[0][0] == "no_workers"


def test_latency_anomaly_only_makes_cluster_suspect():
    hm = HealthModel(W, expected_workers=2)
    for i in range(20):
        hm.assess(obs(ts=i, latency_s=0.01))
    rep = hm.assess(obs(ts=21, latency_s=0.5))
    assert 0.5 < rep.health < 0.95
    sm = HealthStateMachine("A", 0.95, 0.5, 3, 5)
    sm.update(0, rep.health)
    assert sm.state == SUSPECT


def test_weights_are_normalised():
    hm = HealthModel({k: v * 10 for k, v in W.items()}, expected_workers=2)
    assert sum(hm.weights.values()) == pytest.approx(1.0)


def test_state_machine_needs_consecutive_low_polls_and_hysteresis():
    sm = HealthStateMachine("A", suspect_threshold=0.9, failed_threshold=0.5,
                            failed_consecutive=3, recovered_consecutive=2)
    assert sm.update(0, 0.3).new == SUSPECT
    assert sm.update(1, 0.3) is None and sm.state == SUSPECT
    tr = sm.update(2, 0.3)
    assert tr.new == FAILED
    assert sm.update(3, 1.0) is None and sm.state == FAILED     # one good poll is not enough
    assert sm.update(4, 1.0).new == HEALTHY


def test_state_machine_blip_does_not_fail():
    sm = HealthStateMachine("A", 0.9, 0.5, 3, 2)
    for h in (0.3, 0.3, 1.0, 0.3, 0.3):
        sm.update(0, h)
    assert sm.state != FAILED


def test_bad_thresholds_rejected():
    with pytest.raises(ValueError):
        HealthStateMachine("A", 0.4, 0.6, 3, 2)


def test_timeout_detector():
    d = TimeoutDetector("A", timeout_s=30)
    assert d.update(0, False) is None
    assert d.update(29, False) is None
    assert d.update(30, False).new == FAILED
    assert d.update(31, True).new == HEALTHY


def test_placement_prefers_healthy_idle_and_skips_failed():
    views = [ClusterView("A", FAILED, 0.0, 4, 0), ClusterView("B", HEALTHY, 1.0, 4, 2),
             ClusterView("C", SUSPECT, 0.8, 4, 0)]
    p = place(views, 0.4, 0.5, 0.1)
    assert p.cluster == "C"            # J_B = 0.2, J_C = 0.1
    assert "A" not in p.scores
    assert place(views, 0.4, 0.5, 0.1, exclude=("C",)).cluster == "B"


def test_placement_no_candidate():
    assert place([ClusterView("A", FAILED, 0.0, 4, 0)], 0.4, 0.5, 0.1).cluster is None


def test_placement_tie_is_deterministic():
    views = [ClusterView("B", HEALTHY, 1.0, 4, 0), ClusterView("A", HEALTHY, 1.0, 4, 0)]
    assert place(views, 0.4, 0.5, 0.1).cluster == "A"
