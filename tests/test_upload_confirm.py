"""Flusso di conferma upload (/upload/confirm): validazione formale dei campi
(CF, obbligatori), autorizzazione dello scope di destinazione, write-back su
vault (VAULT_PATH) e Notion mockati. La conferma umana resta il presupposto."""
import pytest
from fastapi.testclient import TestClient

from app import extract, main, tenants, writeback
from app.config import settings

client = TestClient(main.app)

FAKE_TENANT = {"name": "ATS", "allowed_scopes": ["ats"], "allowed_origins": [],
               "branding": {}, "quota_day": 0}

FIELDS_OK = {"nome": "Maria", "cognome": "Rossi",
             "codice_fiscale": "RSSMRA85T10A562S",
             "codice_comunicazione": "1234567890", "data_inizio": "13/06/2026",
             "data_fine": "15/06/2026", "tipologia": "Determinato"}


@pytest.fixture(autouse=True)
def _mock_tenant(monkeypatch):
    monkeypatch.setattr(tenants, "get_tenant_by_key",
                        lambda k: FAKE_TENANT if k == "K_ATS" else None)


def _post(body, key="K_ATS"):
    return client.post("/upload/confirm", json=body, headers={"X-Tenant-Key": key})


def test_validate_unilav():
    assert extract.validate_unilav(FIELDS_OK) == []
    probs = extract.validate_unilav({"nome": "", "codice_fiscale": "XXX"})
    assert any("nome" in p for p in probs)
    assert any("cognome" in p for p in probs)
    assert any("codice fiscale non valido" in p for p in probs)
    assert any("codice comunicazione" in p for p in probs)


def test_auth_obbligatoria():
    assert _post({"fields": FIELDS_OK}, key="SBAGLIATA").status_code == 401


def test_scope_non_consentito():
    r = _post({"fields": FIELDS_OK, "cliente": "hrh"})
    assert r.status_code == 403


def test_campi_non_validi_422():
    r = _post({"fields": {**FIELDS_OK, "codice_fiscale": "NONVALIDO"}})
    assert r.status_code == 422 and "codice fiscale" in r.json()["detail"]


def test_consolida_vault_e_notion(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "vault_path", str(tmp_path))
    monkeypatch.setattr(writeback, "notion_upsert", lambda f: {"status": "ok", "page_id": "pg1"})
    r = _post({"fields": FIELDS_OK, "cliente": "ats"})
    assert r.status_code == 200
    b = r.json()
    assert b["consolidato"] is True
    assert b["vault"]["status"] == "ok" and "contratti/" in b["vault"]["path"]
    assert b["notion"]["page_id"] == "pg1"
    nota = tmp_path / b["vault"]["path"]
    assert nota.exists() and "RSSMRA85T10A562S" in nota.read_text("utf-8")


def test_senza_vault_path_skipped(monkeypatch):
    monkeypatch.setattr(settings, "vault_path", "")
    monkeypatch.setattr(writeback, "notion_upsert",
                        lambda f: {"status": "skipped", "reason": "no token"})
    r = _post({"fields": FIELDS_OK})
    assert r.status_code == 200
    b = r.json()
    assert b["consolidato"] is False
    assert b["vault"]["status"] == "skipped" and "VAULT_PATH" in b["vault"]["reason"]


def test_opt_out_dei_target(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "vault_path", str(tmp_path))
    called = {"notion": False}
    monkeypatch.setattr(writeback, "notion_upsert",
                        lambda f: called.__setitem__("notion", True) or {"status": "ok"})
    r = _post({"fields": FIELDS_OK, "notion": False})
    assert r.status_code == 200
    assert r.json()["vault"]["status"] == "ok"
    assert called["notion"] is False and r.json()["notion"]["status"] == "skipped"
