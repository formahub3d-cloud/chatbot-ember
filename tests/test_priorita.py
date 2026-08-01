"""La PRIORITÀ delle task (31-07 sera): 'media' = non ancora giudicata, non
«bassa». Additiva: i tre seed già eseguiti restano validi col default.
Lo script per chiave assegna, non crea: un giudizio su ciò che esiste.
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
def cl(monkeypatch):
    monkeypatch.setattr(settings, "admin_token", TOK)
    monkeypatch.setattr(braintasks, "_mem", [])
    client = TestClient(main.app)

    def get(path):
        r = client.get(path, headers={"Authorization": f"Bearer {TOK}"})
        assert r.status_code == 200, f"{path}: {r.status_code}"
        return r.json()

    def post(path, body):
        r = client.post(path, json=body, headers={"Authorization": f"Bearer {TOK}"})
        assert r.status_code == 200, f"{path}: {r.status_code} {r.text[:200]}"
        return r.json()
    return get, post


def test_priorita_alla_nascita_e_default_media(cl):
    get, post = cl
    r = post("/admin/tasks", {"title": "Urgente", "priorita": "alta",
                              "idempotency_key": "p-alta"})
    assert r["task"]["priorita"] == "alta"
    r2 = post("/admin/tasks", {"title": "Non giudicata", "idempotency_key": "p-def"})
    assert r2["task"]["priorita"] == "media"      # default = onestà, non pigrizia
    r3 = post("/admin/tasks", {"title": "Valore strano", "priorita": "urgentissima",
                               "idempotency_key": "p-strana"})
    assert r3["task"]["priorita"] == "media"      # fuori catalogo → non giudicata
    ts = get("/admin/tasks")["tasks"]
    assert {t["idempotency_key"]: t["priorita"] for t in ts} == {
        "p-alta": "alta", "p-def": "media", "p-strana": "media"}


def test_set_priorita_non_muove_lo_stato(cl):
    get, post = cl
    t = post("/admin/tasks", {"title": "X", "idempotency_key": "p-x"})["task"]
    post("/admin/tasks/priorita", {"id": t["id"], "priorita": "bassa"})
    dopo = get("/admin/tasks")["tasks"][0]
    assert dopo["priorita"] == "bassa" and dopo["status"] == "aperta"


def test_priorita_endpoint_valida(cl):
    get, post = cl
    t = post("/admin/tasks", {"title": "X", "idempotency_key": "p-y"})["task"]
    client = TestClient(main.app)
    r = client.post("/admin/tasks/priorita", json={"id": t["id"], "priorita": "urgente"},
                    headers={"Authorization": f"Bearer {TOK}"})
    assert r.status_code == 422
    r2 = client.post("/admin/tasks/priorita", json={"id": "non-esiste", "priorita": "alta"},
                     headers={"Authorization": f"Bearer {TOK}"})
    assert r2.status_code == 422


def test_transition_porta_la_priorita(cl):
    get, post = cl
    t = post("/admin/tasks", {"title": "X", "idempotency_key": "p-t"})["task"]
    post("/admin/tasks/transition", {"id": t["id"], "to": "fatta", "by": "andrea",
                                     "priorita": "alta"})
    fatta = get("/admin/tasks?status=fatta")["tasks"][0]
    assert fatta["priorita"] == "alta" and fatta["status"] == "fatta"


def test_script_assegna_per_chiave_senza_creare(cl):
    """Le sedici chiavi del prompt (che ne dice 15: 08 e 11 sono due task).
    Le assenti si SALTANO — un giudizio non crea la cosa giudicata."""
    get, post = cl
    _carica("seed_audit", "seed_audit_2026_07_31.py").seed(post)
    _carica("seed_audit_bis", "seed_audit_2026_07_31_bis.py").seed(post)
    _carica("seed_audit_ter", "seed_audit_2026_07_31_ter.py").seed(post)
    prima = len(braintasks._mem)
    mod = _carica("set_priorita", "set_priorita_audit_2026_07_31.py")
    esiti = mod.assegna(get, post)
    assert len(esiti) == 16
    assert all(e["esito"] == "assegnata" for e in esiti)
    assert len(braintasks._mem) == prima                 # NIENTE creato
    per = {t.get("idempotency_key"): t for t in braintasks._mem}
    assert per["audit-2026-07-31-16"]["priorita"] == "alta"
    assert per["audit-2026-07-31-05"]["priorita"] == "media"
    assert per["audit-2026-07-31-04"]["priorita"] == "bassa"
    # le non giudicate restano 'media' (default onesto)
    assert per["audit-2026-07-31-01"]["priorita"] == "media"
    # rilancio: idempotente
    esiti2 = mod.assegna(get, post)
    assert all(e["esito"] == "assegnata" for e in esiti2)
    assert len(braintasks._mem) == prima


def test_script_su_ambiente_vuoto_salta_tutte(cl):
    get, post = cl
    mod = _carica("set_priorita", "set_priorita_audit_2026_07_31.py")
    esiti = mod.assegna(get, post)
    assert all(e["esito"] == "assente, saltata" for e in esiti)
    assert len(braintasks._mem) == 0
