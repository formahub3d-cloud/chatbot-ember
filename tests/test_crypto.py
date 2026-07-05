"""Cifratura contenuti a riposo (GDPR): round-trip, disattivazione senza chiave,
rotazione chiavi, token manomesso, input bytea/memoryview. Nessuna rete."""
import pytest

from app import crypto
from app.config import settings


def test_disabilitato_senza_chiave(monkeypatch):
    monkeypatch.setattr(settings, "content_enc_key", "")
    assert crypto.enabled() is False


def test_round_trip(monkeypatch):
    monkeypatch.setattr(settings, "content_enc_key", crypto.generate_key())
    tok = crypto.encrypt("dati riservati del cliente")
    assert crypto.is_encrypted(tok)
    assert b"dati riservati" not in tok            # davvero cifrato
    assert crypto.decrypt(tok) == "dati riservati del cliente"


def test_rotazione_chiavi(monkeypatch):
    k_old, k_new = crypto.generate_key(), crypto.generate_key()
    monkeypatch.setattr(settings, "content_enc_key", k_old)
    tok = crypto.encrypt("segreto")
    # ruota: nuova chiave primaria, la vecchia resta per decifrare lo storico
    monkeypatch.setattr(settings, "content_enc_key", k_new + "," + k_old)
    assert crypto.decrypt(tok) == "segreto"        # vecchio token ancora leggibile
    assert crypto.decrypt(crypto.encrypt("nuovo")) == "nuovo"


def test_token_manomesso(monkeypatch):
    monkeypatch.setattr(settings, "content_enc_key", crypto.generate_key())
    tok = crypto.encrypt("x")
    with pytest.raises(Exception):
        crypto.decrypt(tok[:-3] + b"AAA")


def test_accetta_memoryview(monkeypatch):
    monkeypatch.setattr(settings, "content_enc_key", crypto.generate_key())
    tok = crypto.encrypt("da bytea")
    assert crypto.decrypt(memoryview(tok)) == "da bytea"   # come arriva da Postgres


def test_is_encrypted_su_testo_in_chiaro():
    assert crypto.is_encrypted("testo normale") is False
    assert crypto.is_encrypted(b"\x00\x01binari") is False
