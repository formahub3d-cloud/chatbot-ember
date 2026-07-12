"""Firma elettronica semplice (SES): record verificabile (chi/quando/cosa=hash),
l'hash cambia se il PDF cambia, i campi mancanti danno 422. Generatore PDF mockato,
nessuna rete."""
import base64

import pytest
from fastapi.testclient import TestClient

from app import contracts, esign, main, tenants

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


# ── unità: hash ─────────────────────────────────────────────────────────────
def test_hash_cambia_se_pdf_cambia():
    assert esign.pdf_hash(b"%PDF-aaa") != esign.pdf_hash(b"%PDF-bbb")
    assert esign.pdf_hash(b"%PDF-aaa") == esign.pdf_hash(b"%PDF-aaa")  # deterministico


def test_hash_pdf_vuoto_solleva():
    with pytest.raises(ValueError):
        esign.pdf_hash(b"")


# ── unità: record ───────────────────────────────────────────────────────────
def test_record_contiene_chi_quando_cosa():
    r = esign.build_record("Maria Rossi", "Al Tuo Servizio S.r.l.s.", "abc123",
                           email="maria@ats.it", ip="1.2.3.4")
    assert r["chi"]["nome"] == "Maria Rossi"
    assert r["chi"]["ragione_sociale"] == "Al Tuo Servizio S.r.l.s."
    assert r["chi"]["email"] == "maria@ats.it" and r["chi"]["ip"] == "1.2.3.4"
    assert r["cosa"]["hash"] == "abc123" and r["cosa"]["algoritmo"] == "sha256"
    assert r["quando"].endswith("+00:00")            # timestamp UTC ISO 8601
    assert r["standard"].startswith("SES")


def test_record_manca_chi_solleva():
    with pytest.raises(ValueError):
        esign.build_record("", "Azienda", "abc", email="a@b.it")
    with pytest.raises(ValueError):
        esign.build_record("Maria", "", "abc", email="a@b.it")


def test_record_manca_identificativo_solleva():
    with pytest.raises(ValueError):
        esign.build_record("Maria", "Azienda", "abc")   # né email né ip


def test_record_manca_hash_solleva():
    with pytest.raises(ValueError):
        esign.build_record("Maria", "Azienda", "", email="a@b.it")


def test_stamp_usa_generatore_pdf(monkeypatch):
    catturato = {}

    def fake_to_pdf(text, titolo="Contratto"):
        catturato["text"] = text
        return b"%PDF-STAMPED"

    monkeypatch.setattr(contracts, "to_pdf", fake_to_pdf)
    rec = esign.build_record("Maria", "Azienda", "deadbeef", ip="1.2.3.4")
    out = esign.stamp("CORPO CONTRATTO", rec, "Determinato")
    assert out == b"%PDF-STAMPED"
    # il timbro riporta il certificato con l'hash del documento
    assert "CERTIFICATO DI FIRMA" in catturato["text"]
    assert "deadbeef" in catturato["text"] and "CORPO CONTRATTO" in catturato["text"]


# ── endpoint ────────────────────────────────────────────────────────────────
def test_sign_ok(monkeypatch):
    # generatore PDF mockato: bytes che dipendono dal testo (così l'hash è legato al PDF)
    monkeypatch.setattr(contracts, "to_pdf",
                        lambda text, titolo="Contratto": ("%PDF-" + text).encode("utf-8", "replace"))
    r = client.post("/contracts/sign",
                    json={"template": "determinato", "data": DATI,
                          "nome": "Maria Rossi", "ragione_sociale": "Al Tuo Servizio S.r.l.s.",
                          "email": "maria@ats.it"},
                    headers=_h())
    assert r.status_code == 200
    b = r.json()
    sig = b["signature"]
    assert sig["chi"]["nome"] == "Maria Rossi"
    assert sig["chi"]["email"] == "maria@ats.it"
    assert sig["chi"]["ip"]                       # IP catturato dalla request (identificativo)
    assert sig["quando"] and sig["cosa"]["hash"] == b["pdf_sha256"]
    assert base64.b64decode(b["pdf_base64"])[:5] == b"%PDF-"


def test_sign_hash_dipende_dai_dati(monkeypatch):
    monkeypatch.setattr(contracts, "to_pdf",
                        lambda text, titolo="Contratto": ("%PDF-" + text).encode("utf-8", "replace"))
    base = {"template": "determinato", "nome": "Maria Rossi",
            "ragione_sociale": "ATS", "email": "m@ats.it"}
    h1 = client.post("/contracts/sign", json={**base, "data": DATI}, headers=_h()).json()["pdf_sha256"]
    dati2 = {**DATI, "retribuzione": "2.000 EUR mensili"}
    h2 = client.post("/contracts/sign", json={**base, "data": dati2}, headers=_h()).json()["pdf_sha256"]
    assert h1 != h2                               # PDF diverso → hash diverso


def test_sign_manca_firmatario_422(monkeypatch):
    monkeypatch.setattr(contracts, "to_pdf", lambda text, titolo="Contratto": b"%PDF-x")
    r = client.post("/contracts/sign",
                    json={"template": "determinato", "data": DATI, "nome": "", "ragione_sociale": ""},
                    headers=_h())
    assert r.status_code == 422 and "obbligatori" in r.json()["detail"]


def test_sign_campi_contratto_mancanti_422(monkeypatch):
    monkeypatch.setattr(contracts, "to_pdf", lambda text, titolo="Contratto": b"%PDF-x")
    r = client.post("/contracts/sign",
                    json={"template": "determinato", "data": {"nome": "x"},
                          "nome": "Maria", "ragione_sociale": "ATS", "email": "m@ats.it"},
                    headers=_h())
    assert r.status_code == 422 and "mancanti" in r.json()["detail"]


def test_sign_template_sconosciuto_404(monkeypatch):
    r = client.post("/contracts/sign",
                    json={"template": "boh", "data": {}, "nome": "Maria", "ragione_sociale": "ATS",
                          "email": "m@ats.it"},
                    headers=_h())
    assert r.status_code == 404


def test_sign_auth_richiesta():
    r = client.post("/contracts/sign",
                    json={"template": "determinato", "data": DATI, "nome": "Maria",
                          "ragione_sociale": "ATS", "email": "m@ats.it"})
    assert r.status_code == 401


def test_sign_company_alias(monkeypatch):
    monkeypatch.setattr(contracts, "to_pdf",
                        lambda text, titolo="Contratto": ("%PDF-" + text).encode("utf-8", "replace"))
    r = client.post("/contracts/sign",
                    json={"template": "determinato", "data": DATI, "nome": "Maria",
                          "company": "ATS Ltd", "email": "m@ats.it"},   # company = alias EN
                    headers=_h())
    assert r.status_code == 200
    assert r.json()["signature"]["chi"]["ragione_sociale"] == "ATS Ltd"
