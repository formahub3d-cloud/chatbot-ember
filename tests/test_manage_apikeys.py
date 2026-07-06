"""Onboarding su api_keys (Supabase): create/brand/revoke/list con DB finto."""
import json

import pytest

from app import manage_apikeys as M, tenants as T
from app.config import settings
from app.security import hash_key


class _Cur:
    def __init__(self, st):
        self.st = st
        self.rowcount = 0
        self._rows = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=()):
        s = " ".join(sql.split()).upper()
        if s.startswith("INSERT INTO API_KEYS"):
            self.st["insert"] = params
        elif s.startswith("UPDATE API_KEYS SET BRANDING"):
            self.st["brand"] = params
            self.rowcount = 1
        elif s.startswith("UPDATE API_KEYS SET ACTIVE=FALSE"):
            self.st["revoke"] = params
            self.rowcount = 2
        elif s.startswith("SELECT NAME, ACTIVE"):
            self._rows = self.st["rows"]

    def fetchall(self):
        return self._rows


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


def _en(monkeypatch, rows=None):
    monkeypatch.setattr(settings, "grants_backend", "supabase")
    monkeypatch.setattr(settings, "database_url", "postgres://mock")
    st = {"rows": rows or []}
    monkeypatch.setattr(T, "_conn", lambda: _Conn(st))
    return st


def test_create_key(monkeypatch):
    st = _en(monkeypatch)
    key = M.create_key("Cliente X", orgs="forma", tenants_="clientex",
                       origins="https://x.it", quota=2000, branding={"title": "Ass X"})
    assert key.startswith("ovy_") and len(key) > 20
    p = st["insert"]
    assert p[0] == hash_key(key)                # key_hash (mai in chiaro nel DB)
    assert p[1] == "Cliente X" and p[2] == 2000
    assert p[3] == ["forma"] and p[4] == ["clientex"] and p[6] == ["https://x.it"]
    assert json.loads(p[7]) == {"title": "Ass X"}   # branding come JSON (cast ::jsonb)
    assert st["committed"]


def test_create_key_senza_branding(monkeypatch):
    st = _en(monkeypatch)
    M.create_key("Y", tenants_="y")
    assert st["insert"][7] is None             # niente branding → NULL


def test_set_branding(monkeypatch):
    st = _en(monkeypatch)
    assert M.set_branding("X", {"accent": "#000"}) == 1
    assert json.loads(st["brand"][0]) == {"accent": "#000"} and st["brand"][1] == "X"


def test_revoke(monkeypatch):
    st = _en(monkeypatch)
    assert M.revoke("X") == 2 and st["revoke"][0] == "X"


def test_list(monkeypatch):
    _en(monkeypatch, rows=[("X", True, ["forma"], ["x"], 2000, True)])
    out = M.list_keys()
    assert out[0]["name"] == "X" and out[0]["branding"] is True


def test_ready_off(monkeypatch):
    monkeypatch.setattr(settings, "grants_backend", "")
    with pytest.raises(SystemExit):
        M._ready()
