"""V8/D2 + V8/E · La chiusura del giro, provata invece che promessa.

Tre script di manutenzione che toccano dati veri in produzione. Girano una volta
sola e non si possono provare a mano senza sporcare la coda: qui si provano
contro il motore vero (TestClient), con la coda in memoria.
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


def _mod(nome):
    spec = importlib.util.spec_from_file_location(nome, ROOT / "scripts" / f"{nome}.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules[nome] = m
    spec.loader.exec_module(m)
    return m


def _trasporto(client):
    def get(path):
        return client.get(path, headers=AUTH).json()

    def post(path, body):
        return client.post(path, headers=AUTH, json=body).json()
    return get, post


# ══════════════════════════════════════════════════════════════════════════
# Il seed delle dieci task nuove
# ══════════════════════════════════════════════════════════════════════════
def test_le_dieci_task_del_giro_esistono_con_chiave_e_priorita(client):
    m = _mod("seed_task_v8_2026_08_02")
    _get, post = _trasporto(client)
    esiti = m.seed(post)
    assert [e["key"] for e in esiti] == [f"audit-2026-08-02-{n}" for n in range(33, 43)]
    per_chiave = {t["idempotency_key"]: t for t in braintasks._mem}
    assert per_chiave["audit-2026-08-02-33"]["priorita"] == "alta"
    assert per_chiave["audit-2026-08-02-41"]["priorita"] == "alta"
    assert per_chiave["audit-2026-08-02-42"]["priorita"] == "bassa"
    assert all(t["status"] == "aperta" for t in braintasks._mem)


def test_la_42_nasce_dichiarando_di_non_essere_lavoro_di_adesso(client):
    m = _mod("seed_task_v8_2026_08_02")
    _get, post = _trasporto(client)
    m.seed(post)
    nota = {t["idempotency_key"]: t["note"] for t in braintasks._mem}["audit-2026-08-02-42"]
    assert "DOPO" in nota and "non da fare" in nota


def test_rilanciare_il_seed_non_duplica(client):
    m = _mod("seed_task_v8_2026_08_02")
    _get, post = _trasporto(client)
    m.seed(post)
    m.seed(post)
    assert len(braintasks._mem) == 10


# ══════════════════════════════════════════════════════════════════════════
# D2 · La task che affermava una cosa falsa
# ══════════════════════════════════════════════════════════════════════════
def test_la_task_falsa_si_archivia_e_nasce_quella_vera(client):
    """Archiviata perché FALSA, non perché fatta — e la nota lo dice, altrimenti
    fra un mese sembrerà una task chiusa."""
    m = _mod("correggi_case_study_2026_08_02")
    get, post = _trasporto(client)
    client.post("/admin/tasks", headers=AUTH, json={
        "title": "Il case study viene da Centioni, non da ATS", "kind": "audit",
        "status": "aperta", "priorita": "alta", "idempotency_key": m.SBAGLIATA})

    e = m.correggi(get, post)
    assert e["archiviata"] is True and e["creata"] is True
    per_chiave = {t["idempotency_key"]: t for t in braintasks._mem}
    vecchia = per_chiave[m.SBAGLIATA]
    assert vecchia["status"] == "archiviata"          # mai cancellata
    assert "FALSA" in vecchia["note"] and "non perché fatta" in vecchia["note"]
    assert m.NUOVA in vecchia["note"]                 # dove è andata a finire
    assert vecchia["closed_by"] == m.FIRMA            # la correzione è di Andrea
    nuova = per_chiave[m.NUOVA]
    assert nuova["status"] == "aperta" and nuova["priorita"] == "media"
    assert "FORMA" in nuova["title"] and m.SBAGLIATA in nuova["note"]


def test_correggere_due_volte_non_fa_danni(client):
    m = _mod("correggi_case_study_2026_08_02")
    get, post = _trasporto(client)
    client.post("/admin/tasks", headers=AUTH, json={
        "title": "vecchia", "kind": "audit", "status": "aperta",
        "idempotency_key": m.SBAGLIATA})
    m.correggi(get, post)
    e2 = m.correggi(get, post)
    assert e2["archiviata"] is False and e2["creata"] is False
    assert len(braintasks._mem) == 2


def test_senza_la_task_sbagliata_quella_vera_nasce_lo_stesso(client):
    """Il fatto vero vale anche se la falsa non c'è (ambiente pulito, seed mai
    girato): non si perde il contenuto per colpa di una precondizione."""
    m = _mod("correggi_case_study_2026_08_02")
    get, post = _trasporto(client)
    e = m.correggi(get, post)
    assert e["archiviata"] is False and e["creata"] is True
    assert any(f"{m.SBAGLIATA} non trovata" in n for n in e["note"])


# ══════════════════════════════════════════════════════════════════════════
# E2 · L'arretrato: lavoro in produzione ancora in DA FARE
# ══════════════════════════════════════════════════════════════════════════
def test_l_arretrato_passa_a_da_verificare_e_non_a_fatta(client):
    """Regola 2 del giro: il massimo che una macchina può fare è «guardala»."""
    m = _mod("da_verificare_arretrati_2026_08_02")
    _get, post = _trasporto(client)
    for k, _ in m.ARRETRATI:
        client.post("/admin/tasks", headers=AUTH, json={
            "title": "lavoro V6/V7", "kind": "audit", "status": "aperta",
            "idempotency_key": k})
    esiti = m.sposta(post)["esiti"]
    assert all(e["esito"] == "mossa" for e in esiti)
    assert {t["status"] for t in braintasks._mem} == {"da-verificare"}
    assert all(not t.get("closed_by") for t in braintasks._mem)


def test_l_arretrato_nomina_esattamente_le_dieci_chiavi_del_lavoro_in_produzione():
    """Le sette del V6 (che il commit a2fd734 non nominò) più le tre del V7
    perse dal primo audit-merge rotto. Nessuna in più: citare una chiave per il
    motivo sbagliato è peggio che non citarla."""
    m = _mod("da_verificare_arretrati_2026_08_02")
    chiavi = [k for k, _ in m.ARRETRATI]
    assert len(chiavi) == len(set(chiavi)) == 10
    assert "audit-2026-07-31-20" not in chiavi      # la voce da telefono NON è fatta
    assert "audit-2026-08-01-31" not in chiavi      # né la sua gemella
    assert "audit-2026-08-01-27" not in chiavi      # retention: mai guardata
    for _k, dove in m.ARRETRATI:
        assert len(dove) > 30, "ogni chiave deve dire DOVE guardare"


def test_rilanciare_l_arretrato_non_riapre_niente(client):
    m = _mod("da_verificare_arretrati_2026_08_02")
    _get, post = _trasporto(client)
    k = m.ARRETRATI[0][0]
    client.post("/admin/tasks", headers=AUTH, json={
        "title": "x", "kind": "audit", "status": "aperta", "idempotency_key": k})
    m.sposta(post)
    braintasks.transition(braintasks._mem[0]["id"], "fatta", by="andrea")
    esiti = {e["chiave"]: e for e in m.sposta(post)["esiti"]}
    assert esiti[k]["esito"] == "gia" and esiti[k]["status"] == "fatta"
