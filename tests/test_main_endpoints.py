"""Test degli endpoint HTTP reali (FastAPI TestClient), senza rete.

Il layer tenant e il RAG/OCR sono mockati: qui si verifica il comportamento
dell'API — auth, rate-limit/quota/origin (_guard), e soprattutto le garanzie
del nuovo /upload: limite di dimensione e pulizia del file temporaneo.
"""
import os

import pytest
from fastapi.testclient import TestClient

from app import main
from app.config import settings

TENANT = {
    "name": "ATS",
    "allowed_scopes": ["ats"],
    "allowed_orgs": [],
    "allowed_sub_tenants": [],
    "allowed_origins": [],   # vuoto = qualsiasi origine (pilota)
    "key_hash": "hash-ats",
    "quota_day": 0,
}


@pytest.fixture
def client(monkeypatch):
    # tenant valido solo per la chiave "CHIAVE_ATS".
    monkeypatch.setattr(main.tenants, "get_tenant_by_key",
                        lambda k: TENANT if k == "CHIAVE_ATS" else None)
    monkeypatch.setattr(main.tenants, "quota_ok", lambda t: True)
    # rate-limit generoso e stato pulito tra i test.
    monkeypatch.setattr(settings, "rate_limit_per_min", 100)
    main._hits.clear()
    with TestClient(main.app) as c:
        yield c


def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_chat_senza_chiave_401(client):
    r = client.post("/chat", json={"message": "ciao"})
    assert r.status_code == 401


def test_chat_chiave_invalida_401(client):
    r = client.post("/chat", json={"message": "ciao"}, headers={"X-Tenant-Key": "SBAGLIATA"})
    assert r.status_code == 401


def test_chat_ok(client, monkeypatch):
    monkeypatch.setattr(main.rag, "answer",
                        lambda msg, grants, history=None: {"answer": "ok", "sources": [], "scopes": ["ats"]})
    r = client.post("/chat", json={"message": "domanda"}, headers={"X-Tenant-Key": "CHIAVE_ATS"})
    assert r.status_code == 200
    assert r.json()["answer"] == "ok"


def test_chat_messaggio_vuoto_422(client):
    r = client.post("/chat", json={"message": "   "}, headers={"X-Tenant-Key": "CHIAVE_ATS"})
    assert r.status_code == 422


def test_chat_rate_limit_429(client, monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_per_min", 1)
    main._hits.clear()
    monkeypatch.setattr(main.rag, "answer",
                        lambda msg, grants, history=None: {"answer": "ok", "sources": [], "scopes": []})
    h = {"X-Tenant-Key": "CHIAVE_ATS"}
    assert client.post("/chat", json={"message": "uno"}, headers=h).status_code == 200
    assert client.post("/chat", json={"message": "due"}, headers=h).status_code == 429


def test_chat_origin_non_consentita_403(client, monkeypatch):
    # tenant con allowlist di origini: una origine fuori lista → 403.
    t = dict(TENANT, allowed_origins=["https://ats.example"])
    monkeypatch.setattr(main.tenants, "get_tenant_by_key",
                        lambda k: t if k == "CHIAVE_ATS" else None)
    r = client.post("/chat", json={"message": "x"},
                    headers={"X-Tenant-Key": "CHIAVE_ATS", "Origin": "https://evil.example"})
    assert r.status_code == 403


# ── /upload: le nuove garanzie (limite dimensione + cleanup del file temp) ──

def test_upload_file_troppo_grande_413(client, monkeypatch):
    monkeypatch.setattr(settings, "max_upload_bytes", 10)
    r = client.post("/upload", headers={"X-Tenant-Key": "CHIAVE_ATS"},
                    files={"file": ("big.pdf", b"x" * 50, "application/pdf")})
    assert r.status_code == 413


def test_upload_pulisce_file_temporaneo(client, monkeypatch):
    """Il file temporaneo scritto per l'OCR non deve mai restare su disco."""
    seen = {}

    def fake_ocr(path, mime="application/pdf"):
        seen["path"] = path
        assert os.path.exists(path)  # durante l'OCR il file esiste
        return "testo"

    monkeypatch.setattr(main.ocr, "ocr_document", fake_ocr)
    monkeypatch.setattr(main.extract, "extract_unilav", lambda text: {"cf": "..."})

    r = client.post("/upload", headers={"X-Tenant-Key": "CHIAVE_ATS"},
                    files={"file": ("doc.pdf", b"%PDF-1.4 dati", "application/pdf")})
    assert r.status_code == 200
    assert r.json()["consolidato"] is False
    # dopo la richiesta il temp file è stato rimosso (fix del leak).
    assert not os.path.exists(seen["path"])


def test_upload_errore_ocr_502_e_cleanup(client, monkeypatch):
    """Se l'OCR fallisce: 502 e comunque nessun file temporaneo lasciato."""
    seen = {}

    def boom(path, mime="application/pdf"):
        seen["path"] = path
        raise RuntimeError("ocr down")

    monkeypatch.setattr(main.ocr, "ocr_document", boom)
    r = client.post("/upload", headers={"X-Tenant-Key": "CHIAVE_ATS"},
                    files={"file": ("doc.pdf", b"%PDF-1.4 dati", "application/pdf")})
    assert r.status_code == 502
    assert not os.path.exists(seen["path"])
