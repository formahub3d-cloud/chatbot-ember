"""N5 · Chiave master '*': vede tutti gli scope, ma SOLO server-side.

Il filtro master (build_filter → None) è già coperto da test_rag_filter; qui si
verifica la difesa in profondità aggiunta in main._reject_master_browser: una
chiave master usata da un browser (Origin presente = widget pubblico) viene
rifiutata con 403, mentre da server (MCP/CLI, senza Origin) passa.
"""
from fastapi.testclient import TestClient

from app import main, rag, tenants

client = TestClient(main.app)

MASTER_TENANT = {"name": "admin", "allowed_scopes": ["*"], "allowed_origins": []}


def test_is_master():
    assert rag.is_master(["*"]) is True
    assert rag.is_master({"allowed_orgs": ["*"]}) is True
    assert rag.is_master({"allowed_scopes": ["ats"]}) is False
    assert rag.is_master(["ats", "hrh"]) is False


def test_master_bloccata_da_browser(monkeypatch):
    monkeypatch.setattr(tenants, "get_tenant_by_key", lambda k: MASTER_TENANT)
    r = client.post("/chat", json={"message": "ciao"},
                    headers={"X-Tenant-Key": "K", "Origin": "https://sito-cliente.it"})
    assert r.status_code == 403 and "master" in r.text.lower()


def test_master_ok_server_side(monkeypatch):
    monkeypatch.setattr(tenants, "get_tenant_by_key", lambda k: MASTER_TENANT)
    monkeypatch.setattr(main, "rate_ok", lambda k: True)
    monkeypatch.setattr(tenants, "quota_ok", lambda t: True)
    monkeypatch.setattr(rag, "answer",
                        lambda *a, **k: {"answer": "ok", "sources": [], "scopes": ["*"]})
    r = client.post("/chat", json={"message": "ciao"}, headers={"X-Tenant-Key": "K"})
    assert r.status_code == 200 and r.json()["answer"] == "ok"


def test_master_bloccata_anche_su_tts(monkeypatch):
    # La guardia sta in _guard, quindi copre tutti gli endpoint tenant (es. /voice/tts).
    monkeypatch.setattr(tenants, "get_tenant_by_key", lambda k: MASTER_TENANT)
    r = client.post("/voice/tts", json={"text": "ciao"},
                    headers={"X-Tenant-Key": "K", "Origin": "https://sito-cliente.it"})
    assert r.status_code == 403 and "master" in r.text.lower()
