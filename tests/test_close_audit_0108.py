"""Chiusura dell'1/08: il giudizio task-per-task, coi freni giusti.

Il conto atteso a fine giro: 12 fatte · 2 in corso · 7 aperte — ma 07 e 18
si chiudono SOLO con la conferma esplicita dello sguardo al pannello
(CONFERMA_VISTA): una task chiusa per sentito dire è peggio di una aperta.
"""
import importlib.util
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import main, braintasks
from app.config import settings

ROOT = Path(__file__).resolve().parents[1]
TOK = "tok-di-test-lungo-abbastanza-123456"


def _carica(nome, file):
    spec = importlib.util.spec_from_file_location(nome, ROOT / "scripts" / file)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[nome] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def post(monkeypatch):
    monkeypatch.setattr(settings, "admin_token", TOK)
    monkeypatch.setattr(braintasks, "_mem", [])
    client = TestClient(main.app)

    def _post(path, body):
        r = client.post(path, json=body,
                        headers={"Authorization": f"Bearer {TOK}"})
        assert r.status_code == 200, f"{path}: {r.status_code} {r.text[:200]}"
        return r.json()
    return _post


def _scenario(post):
    _carica("seed_audit", "seed_audit_2026_07_31.py").seed(post)
    _carica("seed_audit_bis", "seed_audit_2026_07_31_bis.py").seed(post)
    _carica("seed_audit_ter", "seed_audit_2026_07_31_ter.py").seed(post)
    _carica("close_audit", "close_audit_2026_07_31.py").chiudi(post)
    return _carica("close_audit_0108", "close_audit_2026_08_01.py")


def _conta():
    fatte = [t for t in braintasks._mem if t["status"] == "fatta"]
    incorso = [t for t in braintasks._mem if t["status"] in
               ("in-approvazione", "approvata", "in-esecuzione")]
    aperte = [t for t in braintasks._mem if t["status"] == "aperta"]
    return fatte, incorso, aperte


def _per_chiave():
    return {t.get("idempotency_key"): t for t in braintasks._mem}


def test_senza_conferma_07_e_18_restano_aperte(post):
    mod = _scenario(post)
    esiti = mod.aggiorna(post)                       # conferma_vista=False
    per = _per_chiave()
    fatte, incorso, aperte = _conta()
    assert len(fatte) == 10                          # 5 del 31/07 + 5 dell'1/08
    assert per["audit-2026-07-31-07"]["status"] == "aperta"
    assert per["audit-2026-07-31-18"]["status"] == "aperta"
    attese = [e for e in esiti if "IN ATTESA DELLO SGUARDO" in e["esito"]]
    assert {e["key"] for e in attese} == {"audit-2026-07-31-07", "audit-2026-07-31-18"}
    # in corso: 11 e 16, con la nota di stato APPESA alla nota di nascita
    assert per["audit-2026-07-31-11"]["status"] == "in-approvazione"
    assert per["audit-2026-07-31-16"]["status"] == "in-approvazione"
    assert per["audit-2026-07-31-16"]["note"].startswith("Divina risponde, non conversa")
    assert "IN CORSO · Metà fatta" in per["audit-2026-07-31-16"]["note"]


def test_con_conferma_il_conto_torna_12_2_7(post):
    mod = _scenario(post)
    mod.aggiorna(post, conferma_vista=True)
    fatte, incorso, aperte = _conta()
    assert (len(fatte), len(incorso), len(aperte)) == (12, 2, 7)
    per = _per_chiave()
    assert "9.300" in per["audit-2026-07-31-19"]["note"]          # il valore, coi numeri
    assert per["audit-2026-07-31-07"]["closed_by"] == "andrea"
    # le sette aperte sono ESATTAMENTE quelle del giudizio
    chiavi_aperte = {t["idempotency_key"] for t in aperte}
    assert chiavi_aperte == {f"audit-2026-07-31-{n:02d}" for n in (6, 8, 13, 14, 15, 20, 21)}


def test_rilancio_idempotente(post):
    mod = _scenario(post)
    mod.aggiorna(post, conferma_vista=True)
    prima = len(braintasks._mem)
    esiti = mod.aggiorna(post, conferma_vista=True)   # secondo giro
    assert len(braintasks._mem) == prima == 21
    assert all(e["esito"] in ("già chiusa", "già in-approvazione") for e in esiti)
    nota16 = _per_chiave()["audit-2026-07-31-16"]["note"]
    assert nota16.count("IN CORSO · Metà fatta") == 1  # la nota non si accumula
