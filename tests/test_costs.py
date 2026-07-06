"""N3/N4 · Stima costi per tenant + alert su spike (entrambi OFF di default)."""
from fastapi.testclient import TestClient

from app import costs, main, tenants
from app.config import settings

client = TestClient(main.app)


# ── N3 · annotazione costi ────────────────────────────────────────────────────
def test_annotate_off_di_default(monkeypatch):
    monkeypatch.setattr(settings, "cost_per_request_eur", 0.0)
    out = costs.annotate([{"name": "ats", "count": 100}])
    assert out["total_eur"] == 0.0
    assert "cost_eur" not in out["usage"][0]     # tariffa 0 = niente costi


def test_annotate_on(monkeypatch):
    monkeypatch.setattr(settings, "cost_per_request_eur", 0.02)
    out = costs.annotate([{"name": "ats", "count": 100}, {"name": "hrh", "count": 50}])
    assert out["usage"][0]["cost_eur"] == 2.0
    assert out["usage"][1]["cost_eur"] == 1.0
    assert out["total_eur"] == 3.0 and out["currency"] == "EUR"


# ── N4 · spike + alert ────────────────────────────────────────────────────────
def test_spikes_sopra_soglia():
    rows = [{"name": "ats", "cost_eur": 5.0}, {"name": "hrh", "cost_eur": 0.5}]
    over = costs.spikes(rows, threshold=1.0)
    assert [o["name"] for o in over] == ["ats"]


def test_spikes_soglia_zero_disattiva():
    assert costs.spikes([{"name": "ats", "cost_eur": 99}], threshold=0) == []


def test_check_and_alert_segnala_e_notifica(monkeypatch):
    monkeypatch.setattr(settings, "cost_per_request_eur", 0.10)
    monkeypatch.setattr(settings, "cost_alert_daily_eur", 5.0)
    captured = {}
    monkeypatch.setattr(costs.obs, "capture_message", lambda msg, **k: captured.setdefault("msg", msg))
    data = costs.check_and_alert([{"name": "ats", "count": 100}])  # 100 × 0.10 = €10 > 5
    assert data["alerts"] and data["alerts"][0]["name"] == "ats"
    assert "ats" in captured["msg"]


def test_check_and_alert_nessun_alert_sotto_soglia(monkeypatch):
    monkeypatch.setattr(settings, "cost_per_request_eur", 0.01)
    monkeypatch.setattr(settings, "cost_alert_daily_eur", 5.0)
    data = costs.check_and_alert([{"name": "ats", "count": 100}])   # €1 < 5
    assert data["alerts"] == []


# ── endpoint /admin/usage ─────────────────────────────────────────────────────
def test_admin_usage_endpoint_costi(monkeypatch):
    monkeypatch.setattr(settings, "admin_token", "SEG")
    monkeypatch.setattr(settings, "cost_per_request_eur", 0.05)
    monkeypatch.setattr(settings, "cost_alert_daily_eur", 0.0)
    monkeypatch.setattr(tenants, "usage_today", lambda limit=200: [{"name": "ats", "count": 40}])
    assert client.get("/admin/usage").status_code == 401
    r = client.get("/admin/usage", headers={"Authorization": "Bearer SEG"})
    assert r.status_code == 200
    b = r.json()
    assert b["usage"][0]["cost_eur"] == 2.0 and b["total_eur"] == 2.0 and b["alerts"] == []
