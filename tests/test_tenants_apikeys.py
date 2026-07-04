"""Test del backend api_keys (schema OVYON Supabase): risoluzione chiave→grant a
tre livelli e scrittura audit. Connessione Postgres finta, nessuna rete."""
from app import tenants as T
from app.config import settings
from app.security import hash_key


class _FakeCursor:
    def __init__(self, rows_by_key, sink):
        self.rows_by_key = rows_by_key
        self.sink = sink        # lista dove registriamo gli INSERT (audit)
        self._row = None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=()):
        if sql.strip().upper().startswith("SELECT"):
            self._row = self.rows_by_key.get(params[0])   # params[0] = key_hash
        elif "INSERT INTO access_logs" in sql:
            self.sink.append(params)

    def fetchone(self):
        return self._row


class _FakeConn:
    def __init__(self, rows_by_key, sink):
        self.rows_by_key = rows_by_key
        self.sink = sink

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def cursor(self):
        return _FakeCursor(self.rows_by_key, self.sink)

    def commit(self):
        pass


def _row(name, active, quota, orgs, tenants_, subs, origins):
    # ordine colonne = SELECT in resolve_key_apikeys
    return (name, active, quota, orgs, tenants_, subs, origins)


def _setup(monkeypatch, rows_by_key, sink=None):
    sink = sink if sink is not None else []
    monkeypatch.setattr(settings, "grants_backend", "supabase")
    monkeypatch.setattr(settings, "database_url", "postgres://mock")
    monkeypatch.setattr(T, "_conn", lambda: _FakeConn(rows_by_key, sink))
    return sink


def test_resolve_key_grant_tre_livelli(monkeypatch):
    kh = hash_key("K_ATS")
    _setup(monkeypatch, {kh: _row("ATS", True, 0, ["forma"], ["ats"], ["progetti"],
                                  ["https://x.it"])})
    t = T.get_tenant_by_key("K_ATS")
    assert t["name"] == "ATS"
    assert t["allowed_tenants"] == ["ats"] and t["allowed_scopes"] == ["ats"]
    assert t["allowed_orgs"] == ["forma"]
    assert t["allowed_sub_tenants"] == ["progetti"]
    assert t["allowed_origins"] == ["https://x.it"]
    assert t["key_hash"] == kh


def test_chiave_revocata_o_assente(monkeypatch):
    kh = hash_key("K_OFF")
    _setup(monkeypatch, {kh: _row("Off", False, 0, [], ["ats"], [], [])})
    assert T.get_tenant_by_key("K_OFF") is None     # active=false
    assert T.get_tenant_by_key("SCONOSCIUTA") is None


def test_backend_disattivo_non_usa_apikeys(monkeypatch):
    monkeypatch.setattr(settings, "grants_backend", "")
    assert T._apikeys_enabled() is False


def test_log_access_inserisce(monkeypatch):
    kh = hash_key("K_ATS")
    sink = _setup(monkeypatch, {})
    T.log_access(kh, "create", tenant_code="ats", detail="forma/clienti/ats/generati/x.md")
    assert len(sink) == 1
    params = sink[0]
    assert params[0] == kh and params[1] == "create" and params[2] == "ats"


def test_log_access_noop_senza_backend(monkeypatch):
    monkeypatch.setattr(settings, "grants_backend", "")
    sink = []
    monkeypatch.setattr(T, "_conn", lambda: _FakeConn({}, sink))
    T.log_access("kh", "read")           # backend off → nessun insert
    assert sink == []
