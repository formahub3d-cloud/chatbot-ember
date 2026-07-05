"""Operabilità PRO: request_id nell'header, /admin/insights (gap + feedback
negativi per arricchire il cervello), /ready (readiness). Nessuna rete: mock."""
from fastapi.testclient import TestClient

from app import main, tenants, ingest, metrics
from app.config import settings

client = TestClient(main.app)


def test_request_id_presente():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.headers.get("X-Request-ID")


def test_request_id_propagato():
    r = client.get("/health", headers={"X-Request-ID": "abc123"})
    assert r.headers.get("X-Request-ID") == "abc123"


def test_insights_auth_e_contenuto(monkeypatch):
    monkeypatch.setattr(settings, "admin_token", "SEG")
    metrics.reset()
    metrics.bump_gap(["ats"], "domanda senza risposta")
    metrics.bump_feedback(["ats"], False, "risposta debole")
    metrics.bump_feedback(["ats"], True, "buona")            # positivo: non nei negativi
    assert client.get("/admin/insights").status_code == 401
    r = client.get("/admin/insights", headers={"Authorization": "Bearer SEG"})
    assert r.status_code == 200
    b = r.json()
    assert b["gaps"] and b["gaps"][0]["q"] == "domanda senza risposta"
    assert len(b["negative_feedback"]) == 1
    assert b["negative_feedback"][0]["q"] == "risposta debole"
    metrics.reset()


def test_ready_ok(monkeypatch):
    class _C:
        def get_collections(self):
            return object()
    monkeypatch.setattr(ingest, "client", lambda: _C())
    monkeypatch.setattr(tenants, "get_tenant_by_key", lambda k: None)
    r = client.get("/ready")
    assert r.status_code == 200 and r.json()["ready"] is True


def test_ready_503_se_qdrant_giu(monkeypatch):
    def _raise():
        raise RuntimeError("down")
    monkeypatch.setattr(ingest, "client", _raise)
    monkeypatch.setattr(tenants, "get_tenant_by_key", lambda k: None)
    assert client.get("/ready").status_code == 503


def test_metrics_prometheus(monkeypatch):
    monkeypatch.setattr(settings, "admin_token", "SEG")
    metrics.reset()
    metrics.bump_chat(["ats"])
    metrics.bump_gap(["ats"], "domanda")
    assert client.get("/metrics").status_code == 401           # serve il token
    r = client.get("/metrics", headers={"Authorization": "Bearer SEG"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")
    body = r.text
    assert "ember_chat_total 1" in body
    assert 'ember_gap_by_scope_total{scope="ats"} 1' in body
    metrics.reset()
