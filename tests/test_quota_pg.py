"""Quota per tenant sul backend Supabase (key_usage): sotto/oltre soglia,
illimitata a 0, senza key, fail-open. DB finto."""
from app import tenants as T
from app.config import settings


class _Cur:
    def __init__(self, st):
        self.st = st
        self._n = None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=()):
        if "INSERT INTO KEY_USAGE" in " ".join(sql.split()).upper():
            self.st["params"] = params
            self._n = self.st["count"]

    def fetchone(self):
        return (self._n,)


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


def _pg(monkeypatch, count):
    monkeypatch.setattr(settings, "grants_backend", "supabase")
    monkeypatch.setattr(settings, "database_url", "postgres://mock")
    monkeypatch.setattr(settings, "mongo_uri", "")   # niente Mongo → percorso Supabase
    st = {"count": count}
    monkeypatch.setattr(T, "_conn", lambda: _Conn(st))
    return st


def test_illimitata_a_zero(monkeypatch):
    _pg(monkeypatch, 999)
    assert T.quota_ok({"quota_day": 0, "key_hash": "kh"}) is True


def test_sotto_soglia(monkeypatch):
    st = _pg(monkeypatch, 5)
    assert T.quota_ok({"quota_day": 10, "key_hash": "kh"}) is True
    assert st["params"][0] == "kh" and st["committed"]


def test_oltre_soglia(monkeypatch):
    _pg(monkeypatch, 11)
    assert T.quota_ok({"quota_day": 10, "key_hash": "kh"}) is False


def test_senza_key(monkeypatch):
    _pg(monkeypatch, 999)
    assert T.quota_ok({"quota_day": 10}) is True     # niente key_hash → illimitato


def test_fail_open(monkeypatch):
    monkeypatch.setattr(settings, "grants_backend", "supabase")
    monkeypatch.setattr(settings, "database_url", "postgres://mock")
    monkeypatch.setattr(settings, "mongo_uri", "")

    def boom():
        raise RuntimeError("db down")
    monkeypatch.setattr(T, "_conn", boom)
    assert T.quota_ok({"quota_day": 1, "key_hash": "kh"}) is True    # errore → consenti
