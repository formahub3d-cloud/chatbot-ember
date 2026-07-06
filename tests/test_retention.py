"""Retention GDPR: purge_old cancella gli eventi vecchi (rowcount), è off a 0,
accetta un override, e l'endpoint è protetto. DB finto."""
from fastapi.testclient import TestClient

from app import main, events, tenants
from app.config import settings

client = TestClient(main.app)


class _Cur:
    def __init__(self, st):
        self.st = st
        self.rowcount = 0

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=()):
        if " ".join(sql.split()).upper().startswith("DELETE FROM ANALYTICS_EVENTS"):
            self.st["deleted_sql"] = True
            self.rowcount = self.st["would"]


class _Conn:
    def __init__(self, st):
        self.st = st

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def cursor(self):
        return _Cur(self.st)

    def commit(self):
        self.st["committed"] = True


def _db(monkeypatch, would=4):
    monkeypatch.setattr(settings, "grants_backend", "supabase")
    monkeypatch.setattr(settings, "database_url", "postgres://mock")
    st = {"would": would, "deleted_sql": False, "committed": False}
    monkeypatch.setattr(tenants, "_conn", lambda: _Conn(st))
    return st


def test_purge_off_a_zero(monkeypatch):
    st = _db(monkeypatch)
    monkeypatch.setattr(settings, "retention_days", 0)
    assert events.purge_old() == 0 and st["deleted_sql"] is False


def test_purge_cancella(monkeypatch):
    st = _db(monkeypatch, would=7)
    monkeypatch.setattr(settings, "retention_days", 30)
    assert events.purge_old() == 7
    assert st["deleted_sql"] and st["committed"]


def test_purge_override_days(monkeypatch):
    _db(monkeypatch, would=2)
    monkeypatch.setattr(settings, "retention_days", 0)   # default off
    assert events.purge_old(90) == 2                     # override esplicito passa


def test_retention_endpoint(monkeypatch):
    monkeypatch.setattr(settings, "admin_token", "SEG")
    _db(monkeypatch, would=3)
    monkeypatch.setattr(settings, "retention_days", 30)
    assert client.post("/admin/retention/run").status_code == 401
    r = client.post("/admin/retention/run", headers={"Authorization": "Bearer SEG"})
    assert r.status_code == 200 and r.json()["deleted"] == 3
