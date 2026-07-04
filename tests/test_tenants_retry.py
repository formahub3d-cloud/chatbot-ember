"""Regressione: resolve_key_apikeys deve assorbire il drop 'a freddo' del pooler
(prima richiesta dopo inattività) con un retry, senza far fallire una chiave valida.
Un outage reale (entrambi i tentativi falliti) deve invece sollevare, così che
get_tenant_by_key faccia il fallback previsto. Connessione finta, nessuna rete."""
import os

os.environ.setdefault("GRANTS_BACKEND", "supabase")
os.environ.setdefault("DATABASE_URL", "postgresql://x")

from app import tenants as T  # noqa: E402


class _FakeCur:
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def execute(self, *a): pass
    def fetchone(self):
        # name, active, quota_day, orgs, tenants, subs, origins
        return ("ATS", True, 0, [], ["ats"], [], ["https://www.altuoservizio.it"])


class _FakeConn:
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def cursor(self): return _FakeCur()


def test_retry_assorbe_cold_start(monkeypatch):
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] == 1:
            raise Exception("server closed the connection unexpectedly")
        return _FakeConn()

    monkeypatch.setattr(T, "_conn", flaky)
    res = T.resolve_key_apikeys("ember_ats_test")
    assert res is not None
    assert res["allowed_tenants"] == ["ats"]
    assert calls["n"] == 2  # primo fallito + retry riuscito


def test_outage_solleva_dopo_due_tentativi(monkeypatch):
    calls = {"n": 0}

    def always_fail():
        calls["n"] += 1
        raise Exception("db down")

    monkeypatch.setattr(T, "_conn", always_fail)
    try:
        T.resolve_key_apikeys("x")
        assert False, "doveva sollevare per far scattare il fallback"
    except Exception:
        pass
    assert calls["n"] == 2
