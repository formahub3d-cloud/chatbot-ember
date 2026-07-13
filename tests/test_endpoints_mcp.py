"""Test HTTP degli endpoint per il connettore MCP (/search /document /context
/writeback) con Qdrant e store tenant mockati. Esercita auth, guardie e il flusso
anteprima→conferma del write-back."""
import pytest
from fastapi.testclient import TestClient

from app import main, tenants, rag, writeback
from app.config import settings

client = TestClient(main.app)

FAKE_TENANT = {"name": "ATS", "allowed_scopes": ["ats"], "allowed_origins": [],
               "branding": {}, "quota_day": 0}


@pytest.fixture(autouse=True)
def _mock_tenant(monkeypatch):
    monkeypatch.setattr(tenants, "get_tenant_by_key",
                        lambda k: FAKE_TENANT if k == "K_ATS" else None)


def test_auth_obbligatoria():
    assert client.post("/search", json={"message": "x"}).status_code == 401
    assert client.get("/context").status_code == 401


def test_search_ok(monkeypatch):
    monkeypatch.setattr(rag, "search",
                        lambda q, g, k: {"results": [{"slug": "doc-x"}], "scopes": g["allowed_scopes"]})
    r = client.post("/search", json={"message": "ciao", "k": 3}, headers={"X-Tenant-Key": "K_ATS"})
    assert r.status_code == 200
    assert r.json()["results"][0]["slug"] == "doc-x"
    assert r.json()["scopes"] == ["ats"]


def test_context_ok():
    r = client.get("/context", headers={"X-Tenant-Key": "K_ATS"})
    assert r.status_code == 200
    body = r.json()
    assert body["allowed_tenants"] == ["ats"] and body["master"] is False


def test_document_404_fuori_scope(monkeypatch):
    monkeypatch.setattr(rag, "get_document", lambda slug, g: None)
    r = client.get("/document", params={"slug": "segreto"}, headers={"X-Tenant-Key": "K_ATS"})
    assert r.status_code == 404


def test_document_ok(monkeypatch):
    monkeypatch.setattr(rag, "get_document",
                        lambda slug, g: {"slug": slug, "title": "T", "text": "corpo"})
    r = client.get("/document", params={"slug": "doc-x"}, headers={"X-Tenant-Key": "K_ATS"})
    assert r.status_code == 200 and r.json()["text"] == "corpo"


def test_writeback_scope_non_consentito():
    r = client.post("/writeback", json={"scope": "hrh", "title": "X", "body": "y"},
                    headers={"X-Tenant-Key": "K_ATS"})
    assert r.status_code == 403


def test_writeback_anteprima_poi_conferma(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "vault_path", str(tmp_path))

    # 1) senza confirm → solo anteprima, niente file
    r1 = client.post("/writeback", json={"scope": "ats", "title": "Report Q3", "body": "testo"},
                     headers={"X-Tenant-Key": "K_ATS"})
    assert r1.status_code == 200 and r1.json()["consolidato"] is False
    assert "preview" in r1.json()
    assert not (tmp_path / "forma/clienti/ats/generati/report-q3.md").exists()

    # 2) con confirm → scrive nel vault
    r2 = client.post("/writeback",
                     json={"scope": "ats", "title": "Report Q3", "body": "testo", "confirm": True},
                     headers={"X-Tenant-Key": "K_ATS"})
    assert r2.status_code == 200 and r2.json()["consolidato"] is True
    assert (tmp_path / "forma/clienti/ats/generati/report-q3.md").read_text("utf-8").find("testo") >= 0


def test_writeback_auto_reingest_on(tmp_path, monkeypatch):
    """AUTO_REINGEST on: dopo un write-back confermato, la nota è re-indicizzata subito."""
    from app import ingest
    monkeypatch.setattr(settings, "vault_path", str(tmp_path))
    monkeypatch.setattr(settings, "auto_reingest", True)
    seen = {}
    monkeypatch.setattr(ingest, "reindex_paths",
                        lambda paths, **k: seen.update(paths=paths, kw=k) or {"mode": "incremental", "indexed": 1})
    r = client.post("/writeback",
                    json={"scope": "ats", "title": "Nota Live", "body": "testo", "confirm": True},
                    headers={"X-Tenant-Key": "K_ATS"})
    assert r.status_code == 200 and r.json()["consolidato"] is True
    assert seen["paths"] == [r.json()["path"]]          # ha re-indicizzato la nota scritta
    assert seen["kw"].get("sync") is False              # niente git pull sulla copia locale
    assert r.json()["reingest"]["indexed"] == 1


def test_writeback_auto_reingest_off(tmp_path, monkeypatch):
    """Default (off): nessuna re-indicizzazione automatica, comportamento storico."""
    from app import ingest
    monkeypatch.setattr(settings, "vault_path", str(tmp_path))
    monkeypatch.setattr(settings, "auto_reingest", False)
    called = {"v": False}
    monkeypatch.setattr(ingest, "reindex_paths", lambda *a, **k: called.update(v=True) or {})
    r = client.post("/writeback",
                    json={"scope": "ats", "title": "Nota Off", "body": "testo", "confirm": True},
                    headers={"X-Tenant-Key": "K_ATS"})
    assert r.status_code == 200 and r.json()["consolidato"] is True
    assert called["v"] is False and "reingest" not in r.json()
