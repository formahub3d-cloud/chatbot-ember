"""GDPR per tenant: export decifra i contenuti, erase è dry-run senza confirm e
cancella (Qdrant+DB) con confirm. DB e Qdrant finti; crypto reale."""
from datetime import datetime

from fastapi.testclient import TestClient

from app import main, gdpr, tenants, ingest, crypto
from app.config import settings

client = TestClient(main.app)


class _Cur:
    def __init__(self, st):
        self.st = st
        self._rows = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=()):
        s = " ".join(sql.split()).lower()
        if s.startswith("select slug"):
            self._rows = self.st["docs"]
        elif s.startswith("select kind"):
            self._rows = self.st["events"]
        elif "count(*) from documents" in s:
            self._rows = [(len(self.st["docs"]),)]
        elif "count(*) from analytics_events" in s:
            self._rows = [(len(self.st["events"]),)]
        elif s.startswith("delete from documents"):
            self.st["del_docs"] = True
        elif s.startswith("delete from analytics_events"):
            self.st["del_events"] = True

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else (0,)


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


class _QClient:
    def __init__(self, st):
        self.st = st

    def count(self, collection_name, count_filter, exact=True):
        return type("R", (), {"count": self.st["qpoints"]})()

    def delete(self, collection_name, points_selector):
        self.st["qdeleted"] = True


def _setup(monkeypatch, docs=None, events=None, qpoints=3, set_key=True):
    monkeypatch.setattr(settings, "grants_backend", "supabase")
    monkeypatch.setattr(settings, "database_url", "postgres://mock")
    if set_key:
        monkeypatch.setattr(settings, "content_enc_key", crypto.generate_key())
    st = {"docs": docs or [], "events": events or [], "qpoints": qpoints,
          "committed": False, "del_docs": False, "del_events": False, "qdeleted": False}
    monkeypatch.setattr(tenants, "_conn", lambda: _Conn(st))
    monkeypatch.setattr(ingest, "client", lambda: _QClient(st))
    return st


def test_export_decifra(monkeypatch):
    key = crypto.generate_key()
    monkeypatch.setattr(settings, "content_enc_key", key)
    enc = crypto.encrypt("corpo riservato ATS")
    docs = [("sito-ats", "Sito ATS", "forma/clienti/ats/sito.md", ["web"], enc)]
    events = [("gap", "ats", "domanda", datetime(2026, 7, 5, 10, 0, 0))]
    _setup(monkeypatch, docs=docs, events=events, set_key=False)   # chiave già impostata sopra
    out = gdpr.export_tenant("ats")
    assert out["counts"] == {"documents": 1, "events": 1}
    assert out["documents"][0]["content"] == "corpo riservato ATS"   # decifrato
    assert out["documents"][0]["slug"] == "sito-ats"
    assert out["events"][0]["kind"] == "gap"


def test_export_backend_off(monkeypatch):
    monkeypatch.setattr(settings, "grants_backend", "")
    out = gdpr.export_tenant("ats")
    assert out["counts"]["documents"] == 0 and "error" in out


def test_erase_dry_run_non_cancella(monkeypatch):
    monkeypatch.setattr(settings, "admin_token", "SEG")
    st = _setup(monkeypatch, docs=[("s", "t", "p", [], None)],
                events=[("chat", "ats", None, datetime.now())], qpoints=5)
    r = client.post("/admin/gdpr/erase", json={"tenant": "ats"},
                    headers={"Authorization": "Bearer SEG"})
    assert r.status_code == 200
    b = r.json()
    assert b["dry_run"] is True
    assert b["would_erase"]["documents"] == 1 and b["would_erase"]["qdrant_points"] == 5
    assert st["del_docs"] is False and st["qdeleted"] is False       # nulla cancellato


def test_erase_confirm_cancella(monkeypatch):
    monkeypatch.setattr(settings, "admin_token", "SEG")
    st = _setup(monkeypatch, docs=[("s", "t", "p", [], None)], events=[], qpoints=2)
    r = client.post("/admin/gdpr/erase", json={"tenant": "ats", "confirm": True},
                    headers={"Authorization": "Bearer SEG"})
    assert r.status_code == 200
    b = r.json()
    assert b["dry_run"] is False
    assert b["result"]["erased"]["documents"] == 1
    assert st["del_docs"] and st["qdeleted"] and st["committed"]


def test_export_endpoint_auth(monkeypatch):
    monkeypatch.setattr(settings, "admin_token", "SEG")
    _setup(monkeypatch, docs=[], events=[])
    assert client.get("/admin/gdpr/export", params={"tenant": "ats"}).status_code == 401
    r = client.get("/admin/gdpr/export", params={"tenant": "ats"},
                   headers={"Authorization": "Bearer SEG"})
    assert r.status_code == 200 and r.json()["tenant"] == "ats"
