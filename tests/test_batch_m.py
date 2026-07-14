"""Batch M (parti backend): auto-lang, /version, export CSV, guard voice, feedback reason."""
from fastapi.testclient import TestClient

from app import main, rag, tenants, events, security
from app.config import settings

client = TestClient(main.app)


# ── M4 · auto-detect lingua ───────────────────────────────────────────────────
def test_detect_lang():
    assert rag.detect_lang("what is this and how do you work") == "en"
    assert rag.detect_lang("ciao, come stai e cosa puoi fare") == "it"
    assert rag.detect_lang("") == "it"


def test_answer_lang_auto(monkeypatch):
    monkeypatch.setattr(rag, "_retrieve", lambda q, g, k: [])
    assert rag.answer("what is this, how are you", ["ats"], lang="auto")["answer"] == rag._NO_ANSWER_EN
    assert rag.answer("ciao come stai", ["ats"], lang="auto")["answer"] == rag.NO_ANSWER


# ── M5 · /version ─────────────────────────────────────────────────────────────
def test_version(monkeypatch):
    monkeypatch.setattr(settings, "app_version", "1.2.3")
    monkeypatch.setattr(settings, "git_sha", "abcdef1234567890")
    b = client.get("/version").json()
    assert b["version"] == "1.2.3" and b["commit"] == "abcdef123456" and b["name"] == "Divina"


# ── M3 · export CSV ───────────────────────────────────────────────────────────
def test_access_logs_csv(monkeypatch):
    monkeypatch.setattr(settings, "admin_token", "SEG")
    monkeypatch.setattr(tenants, "recent_access_logs",
                        lambda limit=500: [{"at": "2026-07-06", "action": "read", "tenant": "ats", "org": "forma", "detail": "x"}])
    assert client.get("/admin/access-logs.csv").status_code == 401
    r = client.get("/admin/access-logs.csv", headers={"Authorization": "Bearer SEG"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert "action" in r.text and "read" in r.text


def test_events_csv(monkeypatch):
    monkeypatch.setattr(settings, "admin_token", "SEG")
    monkeypatch.setattr(events, "recent", lambda limit=500: [{"at": "t", "kind": "chat", "scope": "ats", "question": "q"}])
    r = client.get("/admin/events.csv", headers={"Authorization": "Bearer SEG"})
    assert r.status_code == 200 and "kind" in r.text and "chat" in r.text


# ── M2 · guard su /voice ──────────────────────────────────────────────────────
def test_voice_tts_guard_429(monkeypatch):
    monkeypatch.setattr(tenants, "get_tenant_by_key", lambda k: {"name": "X", "allowed_origins": []})
    monkeypatch.setattr(security, "origin_allowed", lambda o, a: True)
    monkeypatch.setattr(main, "rate_ok", lambda k: False)
    r = client.post("/voice/tts", json={"text": "ciao"}, headers={"X-Tenant-Key": "K"})
    assert r.status_code == 429 and r.headers.get("Retry-After") == "60"


# ── M6 · feedback con motivo ──────────────────────────────────────────────────
def test_feedback_reason(monkeypatch):
    monkeypatch.setattr(tenants, "get_tenant_by_key", lambda k: {"name": "X", "allowed_origins": [], "allowed_scopes": ["ats"]})
    monkeypatch.setattr(security, "origin_allowed", lambda o, a: True)
    monkeypatch.setattr(main, "rate_ok", lambda k: True)
    monkeypatch.setattr(tenants, "quota_ok", lambda t: True)
    captured = {}
    monkeypatch.setattr(events, "record", lambda kind, scopes, q="": captured.update(kind=kind, q=q))
    r = client.post("/feedback", json={"vote": "down", "question": "quanto costa", "reason": "risposta lenta"},
                    headers={"X-Tenant-Key": "K"})
    assert r.status_code == 200
    assert captured["kind"] == "feedback_down" and "motivo: risposta lenta" in captured["q"]
