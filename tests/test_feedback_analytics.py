"""Endpoint /feedback (autenticato come /chat) e /admin/analytics (Bearer ADMIN_TOKEN).
Store tenant mockato, nessuna rete."""
import pytest
from fastapi.testclient import TestClient

from app import main, tenants, metrics
from app.config import settings

client = TestClient(main.app)

FAKE_TENANT = {"name": "ATS", "allowed_scopes": ["ats"], "allowed_origins": [],
               "branding": {}, "quota_day": 0}


@pytest.fixture(autouse=True)
def _setup(monkeypatch):
    monkeypatch.setattr(tenants, "get_tenant_by_key",
                        lambda k: FAKE_TENANT if k == "K_ATS" else None)
    metrics.reset()
    yield
    metrics.reset()


def test_feedback_richiede_chiave():
    assert client.post("/feedback", json={"vote": "up"}).status_code == 401


def test_feedback_ok_e_conta_per_scope():
    r = client.post("/feedback", json={"vote": "up", "question": "come funziona?"},
                    headers={"X-Tenant-Key": "K_ATS"})
    assert r.status_code == 200 and r.json()["ok"] is True
    r2 = client.post("/feedback", json={"vote": "down"}, headers={"X-Tenant-Key": "K_ATS"})
    assert r2.status_code == 200
    per = metrics.snapshot()["per_scope"]["ats"]
    assert per["feedback_up"] == 1 and per["feedback_down"] == 1


def test_analytics_protetto_da_admin_token(monkeypatch):
    monkeypatch.setattr(settings, "admin_token", "SEGRETO")
    assert client.get("/admin/analytics").status_code == 401
    assert client.get("/admin/analytics",
                      headers={"Authorization": "Bearer sbagliato"}).status_code == 401
    r = client.get("/admin/analytics", headers={"Authorization": "Bearer SEGRETO"})
    assert r.status_code == 200
    body = r.json()
    assert "totals" in body and "per_scope" in body
