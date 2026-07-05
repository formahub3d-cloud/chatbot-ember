"""Persistenza analytics su Supabase: off di default, record/recent con DB finto.
Nessuna rete: si mocka tenants._conn (stesso pattern di test_docstore)."""
from datetime import datetime

from app import events, tenants
from app.config import settings


class _Cur:
    def __init__(self, state):
        self.state = state

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=()):
        if sql.startswith("INSERT INTO analytics_events"):
            self.state["ins"].append(params)
        elif sql.strip().startswith("SELECT"):
            self.state["limit"] = params[0]

    def fetchall(self):
        return self.state["rows"]


class _Conn:
    def __init__(self, state):
        self.state = state

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def cursor(self):
        return _Cur(self.state)

    def commit(self):
        self.state["committed"] = True


def _enable(monkeypatch, rows=None):
    monkeypatch.setattr(settings, "analytics_persist", True)
    monkeypatch.setattr(settings, "grants_backend", "supabase")
    monkeypatch.setattr(settings, "database_url", "postgres://mock")
    state = {"ins": [], "rows": rows or [], "committed": False}
    monkeypatch.setattr(tenants, "_conn", lambda: _Conn(state))
    return state


def test_disabilitato_di_default(monkeypatch):
    monkeypatch.setattr(settings, "analytics_persist", False)
    assert events.enabled() is False
    assert events.record("chat", ["ats"]) is False
    assert events.recent() == []


def test_record_inserisce(monkeypatch):
    state = _enable(monkeypatch)
    ok = events.record("gap", ["ats", "forma-core"], "domanda redatta")
    assert ok is True and state["committed"] is True
    kind, scope, q = state["ins"][0]
    assert kind == "gap" and scope == "ats,forma-core" and q == "domanda redatta"


def test_record_kind_invalido(monkeypatch):
    _enable(monkeypatch)
    assert events.record("boh", ["ats"]) is False


def test_record_scope_vuoto_e_question_none(monkeypatch):
    state = _enable(monkeypatch)
    events.record("chat", [])
    kind, scope, q = state["ins"][0]
    assert scope == "∅" and q is None


def test_recent_parsa_le_righe(monkeypatch):
    now = datetime(2026, 7, 5, 12, 0, 0)
    _enable(monkeypatch, rows=[("gap", "ats", "q1", now)])
    out = events.recent(10)
    assert out[0]["kind"] == "gap" and out[0]["scope"] == "ats"
    assert out[0]["at"].startswith("2026-07-05")
