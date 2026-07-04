"""Test dell'helper RLS (GUC ovyon.* via set_config). Connessione Postgres finta."""
from app import rls


class _FakeCursor:
    def __init__(self, sink, count=0):
        self.sink = sink        # registra (sql, params)
        self.count = count

    def execute(self, sql, params=()):
        self.sink.append((sql, params))

    def fetchone(self):
        return (self.count,)


class _FakeConn:
    def __init__(self, sink, count=0):
        self.sink = sink
        self.count = count
        self.committed = False
        self.closed = False

    def cursor(self):
        return _FakeCursor(self.sink, self.count)

    def commit(self):
        self.committed = True

    def close(self):
        self.closed = True


def test_guc_values_liste_e_dict():
    v = rls.guc_values({"allowed_orgs": ["forma"], "allowed_tenants": ["ats", "hrh"]})
    assert v["ovyon.allowed_orgs"] == "forma"
    assert v["ovyon.allowed_tenants"] == "ats,hrh"
    assert v["ovyon.allowed_sub_tenants"] == ""
    # lista storica = allowed_tenants
    assert rls.guc_values(["ats"])["ovyon.allowed_tenants"] == "ats"


def test_set_grants_emette_set_config():
    sink = []
    rls.set_grants(_FakeCursor(sink), {"allowed_tenants": ["ats"], "allowed_orgs": ["forma"]})
    stmts = {p[0]: p[1] for (sql, p) in sink}   # {guc_name: value}
    assert all("set_config" in sql for sql, _ in sink)
    assert stmts["ovyon.allowed_tenants"] == "ats"
    assert stmts["ovyon.allowed_orgs"] == "forma"
    # il terzo argomento di set_config è True (is_local)
    assert all(len(p) == 3 and p[2] is True for _, p in sink)


def test_session_grants_commit_e_close(monkeypatch):
    sink = []
    conn = _FakeConn(sink)
    monkeypatch.setattr(rls, "_conn", lambda: conn)
    with rls.session_grants(["ats"]) as (c, cur):
        assert c is conn
    assert conn.committed and conn.closed
    assert len(sink) == 3   # 3 GUC impostati


def test_count_documents(monkeypatch):
    conn = _FakeConn([], count=7)
    monkeypatch.setattr(rls, "_conn", lambda: conn)
    assert rls.count_documents(["ats"]) == 7
    assert conn.closed
