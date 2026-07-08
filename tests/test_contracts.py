"""Auto-compilazione contratti: catalogo template, merge dati (missing sui campi
obbligatori), generazione PDF e guardie degli endpoint."""
import pytest
from fastapi.testclient import TestClient

from app import contracts, main, tenants

client = TestClient(main.app)

FAKE_TENANT = {"name": "ATS", "allowed_scopes": ["ats"], "allowed_origins": [],
               "branding": {}, "quota_day": 0}

DATI = {"nome": "Maria", "cognome": "Rossi", "codice_fiscale": "RSSMRA85T10A562S",
        "datore": "Al Tuo Servizio S.r.l.s.", "sede_lavoro": "Benevento",
        "mansione": "Cameriera ai piani", "ccnl": "Turismo e Pubblici Esercizi",
        "orario": "40 ore settimanali", "retribuzione": "1.650 EUR mensili",
        "data_inizio": "01/08/2026", "data_fine": "30/09/2026"}


@pytest.fixture(autouse=True)
def _mock_tenant(monkeypatch):
    monkeypatch.setattr(tenants, "get_tenant_by_key",
                        lambda k: FAKE_TENANT if k == "K_ATS" else None)


def _h():
    return {"X-Tenant-Key": "K_ATS"}


def test_catalogo_template():
    ids = {t["id"] for t in contracts.list_templates()}
    assert {"determinato", "indeterminato", "apprendistato", "stagionale"} <= ids
    det = next(t for t in contracts.list_templates() if t["id"] == "determinato")
    req = {f["name"] for f in det["fields"] if f["required"]}
    assert {"nome", "cognome", "codice_fiscale", "data_inizio", "data_fine"} <= req


def test_fill_completo():
    out = contracts.fill("determinato", DATI)
    assert out["missing"] == []
    assert "Maria" in out["text"] and "RSSMRA85T10A562S" in out["text"]
    assert "dal 01/08/2026 al 30/09/2026" in out["text"]


def test_fill_incompleto_segnala_missing():
    out = contracts.fill("indeterminato", {"nome": "Maria"})
    assert "cognome" in out["missing"] and "datore" in out["missing"]
    assert "___" in out["text"]                      # buchi visibili nella bozza


def test_fill_template_sconosciuto():
    with pytest.raises(KeyError):
        contracts.fill("cococo", {})


def test_pdf_bytes():
    out = contracts.fill("determinato", DATI)
    pdf = contracts.to_pdf(out["text"])
    assert pdf[:5] == b"%PDF-" and len(pdf) > 800


def test_endpoint_auth_e_flusso():
    assert client.get("/contracts/templates").status_code == 401
    r = client.get("/contracts/templates", headers=_h())
    assert r.status_code == 200 and len(r.json()["templates"]) >= 4

    r = client.post("/contracts/fill", json={"template": "determinato", "data": DATI}, headers=_h())
    assert r.status_code == 200 and r.json()["missing"] == []

    r = client.post("/contracts/fill", json={"template": "boh", "data": {}}, headers=_h())
    assert r.status_code == 404

    r = client.post("/contracts/pdf", json={"template": "determinato", "data": {"nome": "x"}}, headers=_h())
    assert r.status_code == 422 and "mancanti" in r.json()["detail"]

    r = client.post("/contracts/pdf", json={"template": "determinato", "data": DATI}, headers=_h())
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:5] == b"%PDF-"
