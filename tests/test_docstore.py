"""Test del sync metadati su Supabase (documents). Connessione Postgres finta:
verifica get-or-create di org/tenant/sub, upsert documenti, caching e no-op."""
from app import docstore
from app import tenants
from app.config import settings


class _FakeCursor:
    """Simula RETURNING per organizations/tenants/sub_tenants e registra i documenti."""
    def __init__(self, state):
        self.state = state
        self._ret = None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=()):
        if "INSERT INTO organizations" in sql:
            self._ret = ("org-" + params[0],)
        elif "INSERT INTO tenants" in sql:
            self._ret = ("ten-" + params[0],)
        elif "INSERT INTO sub_tenants" in sql:
            self._ret = ("sub-" + params[0],)
        elif "INSERT INTO documents" in sql:
            self.state["docs"].append(params)
            self._ret = None

    def fetchone(self):
        return self._ret


class _FakeConn:
    def __init__(self, state):
        self.state = state

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def cursor(self):
        return _FakeCursor(self.state)

    def commit(self):
        self.state["committed"] = True


def _enable(monkeypatch):
    monkeypatch.setattr(settings, "grants_backend", "supabase")
    monkeypatch.setattr(settings, "database_url", "postgres://mock")
    state = {"docs": [], "committed": False}
    monkeypatch.setattr(tenants, "_conn", lambda: _FakeConn(state))
    return state


def test_parse_tags():
    assert docstore.parse_tags("[forma, ai, cat/doc]") == ["forma", "ai", "cat/doc"]
    assert docstore.parse_tags(["a", " b "]) == ["a", "b"]
    assert docstore.parse_tags("") == []


def test_content_id_deterministico():
    a = docstore.content_id_for("forma/clienti/ats/x.md")
    assert a == docstore.content_id_for("forma/clienti/ats/x.md")
    assert a != docstore.content_id_for("forma/clienti/ats/y.md")


def test_sync_notes_upsert_e_mappatura(monkeypatch):
    state = _enable(monkeypatch)
    notes = [
        {"org": "forma", "tenant": "ats", "sub_tenant": "progetti",
         "slug": "sito-ats", "title": "Sito ATS", "path": "forma/clienti/ats/progetti/sito.md",
         "tags": "[forma, web]"},
        {"org": "ovyon", "tenant": "ovyon", "sub_tenant": None,
         "slug": "self-ovyon", "title": "OVYON", "path": "ovyon/self-ovyon.md", "tags": []},
    ]
    n = docstore.sync_notes(notes)
    assert n == 2 and state["committed"] is True
    assert len(state["docs"]) == 2

    d0 = state["docs"][0]   # colonne: content_id, sub_id, tenant_id, org_id, org_code, tenant_code, sub_code, slug, title, path, type, tags
    assert d0[2] == "ten-ats" and d0[3] == "org-forma" and d0[1] == "sub-progetti"
    assert d0[4] == "forma" and d0[5] == "ats" and d0[6] == "progetti"
    assert d0[7] == "sito-ats" and d0[10] == "markdown" and d0[11] == ["forma", "web"]

    d1 = state["docs"][1]   # sub_tenant None → sub_id None
    assert d1[1] is None and d1[6] is None and d1[5] == "ovyon"


def test_sync_notes_noop_senza_backend(monkeypatch):
    monkeypatch.setattr(settings, "grants_backend", "")
    assert docstore.sync_notes([{"org": "x", "tenant": "y", "slug": "s", "path": "p"}]) == 0
    assert docstore.enabled() is False


def test_content_encrypted_senza_chiave(monkeypatch):
    state = _enable(monkeypatch)
    monkeypatch.setattr(settings, "content_enc_key", "")           # cifratura off
    docstore.sync_notes([{"org": "forma", "tenant": "ats", "sub_tenant": None,
                          "slug": "s", "title": "S", "path": "p.md", "tags": [],
                          "content": "corpo riservato"}])
    assert state["docs"][0][12] is None                            # colonna content_encrypted NULL


def test_content_encrypted_con_chiave(monkeypatch):
    from app import crypto
    state = _enable(monkeypatch)
    monkeypatch.setattr(settings, "content_enc_key", crypto.generate_key())
    docstore.sync_notes([{"org": "forma", "tenant": "ats", "sub_tenant": None,
                          "slug": "s", "title": "S", "path": "p.md", "tags": [],
                          "content": "corpo riservato"}])
    tok = state["docs"][0][12]
    assert isinstance(tok, (bytes, bytearray)) and crypto.is_encrypted(tok)
    assert crypto.decrypt(tok) == "corpo riservato"                # round-trip verificato
