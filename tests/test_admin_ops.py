"""Endpoint ops admin (usage, access-logs, status) + header Retry-After sul 429."""
from fastapi.testclient import TestClient

from app import main, tenants, security
from app.config import settings

client = TestClient(main.app)


def _adm(monkeypatch):
    monkeypatch.setattr(settings, "admin_token", "SEG")


def _h():
    return {"Authorization": "Bearer SEG"}


def test_usage(monkeypatch):
    _adm(monkeypatch)
    monkeypatch.setattr(tenants, "usage_today", lambda limit=200: [{"name": "ATS", "count": 42}])
    assert client.get("/admin/usage").status_code == 401
    r = client.get("/admin/usage", headers=_h())
    assert r.status_code == 200 and r.json()["usage"][0]["name"] == "ATS"


def test_access_logs(monkeypatch):
    _adm(monkeypatch)
    monkeypatch.setattr(tenants, "recent_access_logs", lambda limit=100: [{"action": "read", "tenant": "ats"}])
    r = client.get("/admin/access-logs", headers=_h())
    assert r.status_code == 200 and r.json()["logs"][0]["action"] == "read"


def test_status(monkeypatch):
    _adm(monkeypatch)
    monkeypatch.setattr(tenants, "_apikeys_enabled", lambda: True)
    monkeypatch.setattr(settings, "redis_url", "redis://x")
    b = client.get("/admin/status", headers=_h()).json()
    assert b["supabase"] is True and b["redis"] is True
    assert "content_encryption" in b and "default_lang" in b


def test_retry_after_rate(monkeypatch):
    monkeypatch.setattr(tenants, "get_tenant_by_key", lambda k: {"name": "X", "allowed_origins": []})
    monkeypatch.setattr(security, "origin_allowed", lambda o, a: True)
    monkeypatch.setattr(main, "rate_ok", lambda k: False)
    r = client.post("/search", json={"message": "ciao"}, headers={"X-Tenant-Key": "K"})
    assert r.status_code == 429 and r.headers.get("Retry-After") == "60"


def test_retry_after_quota(monkeypatch):
    monkeypatch.setattr(tenants, "get_tenant_by_key", lambda k: {"name": "X", "allowed_origins": []})
    monkeypatch.setattr(security, "origin_allowed", lambda o, a: True)
    monkeypatch.setattr(main, "rate_ok", lambda k: True)
    monkeypatch.setattr(tenants, "quota_ok", lambda t: False)
    r = client.post("/search", json={"message": "ciao"}, headers={"X-Tenant-Key": "K"})
    assert r.status_code == 429 and int(r.headers.get("Retry-After", "0")) > 0
