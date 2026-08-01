"""V7/C · Il merge aggiorna l'audit, ma NON chiude niente.

La semantica è di Andrea e non è negoziabile: una PR mergiata mette le task che
nomina «da verificare». «Fatta» resta una parola che scrive una persona, col suo
nome, dopo aver guardato. Se il merge chiudesse da solo, il pannello direbbe
«fatto» su cose che nessuno ha aperto — ed è esattamente il modo in cui erano
nate le tre affermazioni sbagliate corrette l'1/08.
"""
import importlib.util
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import braintasks, main
from app.config import settings

ROOT = Path(__file__).resolve().parents[1]
TOK = "tok-di-test-lungo-abbastanza-123456"
AUTH = {"Authorization": f"Bearer {TOK}"}


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(settings, "admin_token", TOK)
    monkeypatch.setattr(braintasks, "_mem", [])
    return TestClient(main.app)


def _crea(client, chiave, titolo="Una task"):
    r = client.post("/admin/tasks", headers=AUTH, json={
        "title": titolo, "kind": "audit", "status": "aperta", "idempotency_key": chiave})
    assert r.status_code == 200
    return r.json()["task"]


# ── Il cuore: il merge muove, non chiude ────────────────────────────────────
def test_il_merge_mette_da_verificare_e_non_chiude(client):
    _crea(client, "audit-2026-08-01-22", "Il muro diventa una porta")
    r = client.post("/admin/tasks/da-merge", headers=AUTH, json={
        "pr": "#48", "titolo": "V6 · L'orbita", "chiavi": ["audit-2026-08-01-22"]})
    assert r.status_code == 200
    assert r.json()["esiti"][0]["esito"] == "mossa"
    t = braintasks._mem[0]
    assert t["status"] == "da-verificare"      # NON "fatta"
    assert not t.get("closed_by")              # nessuno l'ha chiusa
    assert "#48" in t["note"] and "DA VERIFICARE" in t["note"]


def test_da_verificare_non_richiede_una_firma_fatta_si(client):
    """È l'unica transizione che una macchina può fare da sola, perché non
    afferma che sia fatta: afferma che qualcuno dovrebbe guardarla."""
    t = _crea(client, "k1")
    assert braintasks.transition(t["id"], "da-verificare") is True     # senza `by`
    assert braintasks.transition(t["id"], "fatta") is False            # serve il nome
    assert braintasks.transition(t["id"], "fatta", by="Andrea") is True


def test_da_verificare_si_puo_rimandare_indietro(client):
    """Guardare e non essere convinti è un esito, e torna in DA FARE."""
    t = _crea(client, "k2")
    braintasks.transition(t["id"], "da-verificare")
    assert braintasks.transition(t["id"], "aperta", note="non ancora a posto") is True
    assert braintasks._mem[0]["status"] == "aperta"


def test_rilanciare_il_merge_non_fa_danni(client):
    _crea(client, "k3")
    client.post("/admin/tasks/da-merge", headers=AUTH, json={"chiavi": ["k3"]})
    r = client.post("/admin/tasks/da-merge", headers=AUTH, json={"chiavi": ["k3"]})
    assert r.json()["esiti"][0]["esito"] == "gia"


def test_una_task_gia_fatta_non_si_riapre(client):
    t = _crea(client, "k4")
    braintasks.transition(t["id"], "fatta", by="Andrea")
    r = client.post("/admin/tasks/da-merge", headers=AUTH, json={"chiavi": ["k4"]})
    assert r.json()["esiti"][0] == {"chiave": "k4", "esito": "gia", "status": "fatta"}


def test_una_chiave_sconosciuta_si_segnala_e_non_si_inventa(client):
    """Una PR può nominare una task di un altro repo: si dice e si va avanti."""
    r = client.post("/admin/tasks/da-merge", headers=AUTH, json={"chiavi": ["mai-vista"]})
    assert r.json()["esiti"][0]["esito"] == "sconosciuta"
    assert braintasks._mem == []               # NIENTE è stato creato


def test_da_merge_e_solo_admin(client):
    assert client.post("/admin/tasks/da-merge", json={"chiavi": []}).status_code == 401


# ── Lo script che legge il messaggio di merge ───────────────────────────────
def _script():
    spec = importlib.util.spec_from_file_location(
        "audit_da_merge", ROOT / "scripts" / "audit_da_merge.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules["audit_da_merge"] = m
    spec.loader.exec_module(m)
    return m


MSG = """Merge pull request #48 from formahub3d-cloud/claude/orbita

V6 · L'orbita che si guarda

Chiude il muro (audit-2026-08-01-22) e il tono (audit-2026-08-01-23).
Vedi anche audit-2026-08-01-22, già citata sopra."""


def test_le_chiavi_si_estraggono_dal_messaggio_senza_doppioni():
    m = _script()
    assert m.chiavi_da(MSG) == ["audit-2026-08-01-22", "audit-2026-08-01-23"]
    assert m.pr_da(MSG) == "#48"
    assert m.titolo_da(MSG) == "V6 · L'orbita che si guarda"


def test_un_merge_che_non_cita_niente_non_fa_niente():
    m = _script()
    assert m.chiavi_da("Merge pull request #7\n\nrifiniture varie") == []
    assert m.chiavi_da("") == []


def test_non_confonde_una_data_con_una_chiave():
    m = _script()
    assert m.chiavi_da("scritto il 2026-08-01 alle 23-40") == []


# ── Il doppione -31 / -20 ───────────────────────────────────────────────────
def _unifica():
    spec = importlib.util.spec_from_file_location(
        "unifica_voce", ROOT / "scripts" / "unifica_voce_telefono.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules["unifica_voce"] = m
    spec.loader.exec_module(m)
    return m


def test_sopravvive_la_piu_vecchia_e_laltra_si_archivia(client):
    mod = _unifica()
    _crea(client, mod.SOPRAVVIVE, "Provare la voce su telefono")
    _crea(client, mod.ARCHIVIA, "La voce provata da un telefono vero")

    def get(path):
        return client.get(path, headers=AUTH).json()

    def post(path, body):
        return client.post(path, headers=AUTH, json=body).json()

    e = mod.unifica(get, post)
    assert e["archiviata"] is True and e["annotata"] is True
    per_chiave = {t["idempotency_key"]: t for t in braintasks._mem}
    assert per_chiave[mod.ARCHIVIA]["status"] == "archiviata"
    assert mod.SOPRAVVIVE in per_chiave[mod.ARCHIVIA]["note"]      # nomina la gemella
    assert per_chiave[mod.SOPRAVVIVE]["status"] == "aperta"        # la vecchia resta viva
    assert mod.ARCHIVIA in per_chiave[mod.SOPRAVVIVE]["note"]

    e2 = mod.unifica(get, post)                                    # idempotente
    assert e2["archiviata"] is False and e2["annotata"] is False
