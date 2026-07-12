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
        self._row = None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=()):
        s = " ".join(sql.split()).upper()
        if s.startswith("DELETE FROM ANALYTICS_EVENTS"):
            self.st["deleted_sql"] = True
            self.rowcount = self.st["would"]
        elif s.startswith("SELECT COUNT(*) FROM ANALYTICS_EVENTS"):
            self.st["preview_sql"] = True
            self._row = (self.st["would"],)

    def fetchone(self):
        return self._row


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
    st = {"would": would, "deleted_sql": False, "preview_sql": False, "committed": False}
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


def test_preview_conta_senza_cancellare(monkeypatch):
    st = _db(monkeypatch, would=5)
    monkeypatch.setattr(settings, "retention_days", 30)
    assert events.preview_old() == 5
    assert st["preview_sql"] and st["deleted_sql"] is False and st["committed"] is False


def test_preview_off_a_zero(monkeypatch):
    st = _db(monkeypatch, would=9)
    monkeypatch.setattr(settings, "retention_days", 0)
    assert events.preview_old() == 0 and st["preview_sql"] is False


def test_preview_override_days(monkeypatch):
    _db(monkeypatch, would=6)
    monkeypatch.setattr(settings, "retention_days", 0)   # default off
    assert events.preview_old(90) == 6                   # override esplicito passa


def test_retention_endpoint_dry_run(monkeypatch):
    monkeypatch.setattr(settings, "admin_token", "SEG")
    st = _db(monkeypatch, would=4)
    monkeypatch.setattr(settings, "retention_days", 30)
    r = client.post("/admin/retention/run", params={"dry_run": True},
                    headers={"Authorization": "Bearer SEG"})
    assert r.status_code == 200
    b = r.json()
    assert b["dry_run"] is True and b["would_delete"] == 4
    assert st["deleted_sql"] is False and st["committed"] is False   # nulla cancellato
