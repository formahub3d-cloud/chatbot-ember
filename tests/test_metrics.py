"""Metriche in-memory per scope: aggregazione totali + dettaglio."""
from app import metrics


def test_snapshot_aggrega_per_scope():
    metrics.reset()
    metrics.bump_chat(["ats"])
    metrics.bump_chat(["ats"])
    metrics.bump_gap(["ats"])
    metrics.bump_feedback(["ats"], True)
    metrics.bump_feedback(["ats"], False)
    metrics.bump_chat(["forma-core", "andrea"])

    s = metrics.snapshot()
    assert s["totals"]["chat"] == 3
    assert s["totals"]["gap"] == 1
    assert s["totals"]["feedback_up"] == 1
    assert s["totals"]["feedback_down"] == 1
    assert s["per_scope"]["ats"]["chat"] == 2
    assert s["per_scope"]["ats"]["gap"] == 1
    # chiave-scope ordinata e stabile
    assert "andrea,forma-core" in s["per_scope"]
    assert isinstance(s["uptime_s"], int)
    metrics.reset()


def test_scope_vuoto_e_reset():
    metrics.reset()
    metrics.bump_chat([])          # nessuno scope → '∅'
    assert metrics.snapshot()["per_scope"]["∅"]["chat"] == 1
    metrics.reset()
    assert metrics.snapshot()["totals"]["chat"] == 0
