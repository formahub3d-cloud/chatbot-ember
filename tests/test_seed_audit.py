"""M2 · Le otto task dell'audit come DATI: seed idempotente, 01 in corso.

Il seed gira qui contro l'app vera (TestClient) col fallback in-memory di
brain_tasks: stessa logica della produzione, zero rete. Se le otto righe
fossero HTML scritto a mano nella pagina, fra una settimana mentirebbero.
"""
import importlib.util
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import main, braintasks
from app.config import settings

ROOT = Path(__file__).resolve().parents[1]


def _carica_seed():
    spec = importlib.util.spec_from_file_location(
        "seed_audit", ROOT / "scripts" / "seed_audit_2026_07_31.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["seed_audit"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def post(monkeypatch):
    monkeypatch.setattr(settings, "admin_token", "tok-di-test-lungo-abbastanza-123456")
    monkeypatch.setattr(braintasks, "_mem", [])          # coda pulita, fallback memoria
    client = TestClient(main.app)

    def _post(path, body):
        r = client.post(path, json=body,
                        headers={"Authorization": "Bearer tok-di-test-lungo-abbastanza-123456"})
        assert r.status_code == 200, f"{path}: {r.status_code} {r.text[:200]}"
        return r.json()
    return _post


def test_seed_crea_le_otto_task_e_la_01_e_in_corso(post):
    mod = _carica_seed()
    esiti = mod.seed(post)
    assert len(esiti) == 8
    assert [e["key"] for e in esiti] == [k for k, *_ in mod.AUDIT_2026_07_31]
    assert esiti[0]["status"] == "in-approvazione"        # la 01 nasce IN CORSO
    assert all(e["status"] == "aperta" for e in esiti[1:])
    # i titoli sono quelli dell'audit, non riformulati
    titoli = [t["title"] for t in braintasks._mem]
    assert "Aggiusta l'orb invisibile e il modo vocale che si chiude" in titoli
    assert "Traduci le quarantadue skill in italiano, e chiamale col lavoro che fanno" in titoli
    assert all(t["kind"] == "audit" for t in braintasks._mem)


def test_seed_rilanciato_non_duplica(post):
    mod = _carica_seed()
    mod.seed(post)
    prima = len(braintasks._mem)
    mod.seed(post)                                        # rilancio: stesse chiavi
    assert len(braintasks._mem) == prima == 8             # idempotenza vera, zero duplicati


def _carica_seed_bis():
    spec = importlib.util.spec_from_file_location(
        "seed_audit_bis", ROOT / "scripts" / "seed_audit_2026_07_31_bis.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["seed_audit_bis"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_seed_bis_crea_le_sette_task_e_la_09_e_in_corso(post):
    """P1: il secondo seed è un file NUOVO (il primo è già girato in produzione
    e resta riproducibile com'era); 7 task 09-15, la 09 in corso (è P2)."""
    mod = _carica_seed_bis()
    esiti = mod.seed(post)
    assert len(esiti) == 7
    assert [e["key"] for e in esiti] == [f"audit-2026-07-31-{n:02d}" for n in range(9, 16)]
    assert esiti[0]["status"] == "in-approvazione"
    assert all(e["status"] == "aperta" for e in esiti[1:])
    titoli = [t["title"] for t in braintasks._mem]
    assert "Il barge-in si riazzera a ogni frase invece che a ogni turno" in titoli
    assert "Decidere quale console è quella vera" in titoli


def test_seed_bis_rilanciato_non_duplica_e_convive_col_primo(post):
    mod1 = _carica_seed()
    mod2 = _carica_seed_bis()
    mod1.seed(post); mod2.seed(post)
    prima = len(braintasks._mem)
    mod2.seed(post)                          # rilancio del bis: zero duplicati
    assert len(braintasks._mem) == prima == 15   # 8 del primo + 7 del bis


def _carica_seed_ter():
    spec = importlib.util.spec_from_file_location(
        "seed_audit_ter", ROOT / "scripts" / "seed_audit_2026_07_31_ter.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["seed_audit_ter"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_seed_ter_crea_le_sei_task_tutte_da_fare(post):
    """X2: terzo seed, file NUOVO (i primi due restano riproducibili com'erano);
    6 task 16-21, tutte DA FARE (nessuna nasce in corso), la 19 è solo Andrea."""
    mod = _carica_seed_ter()
    esiti = mod.seed(post)
    assert len(esiti) == 6
    assert [e["key"] for e in esiti] == [f"audit-2026-07-31-{n}" for n in range(16, 22)]
    assert all(e["status"] == "aperta" for e in esiti)
    titoli = [t["title"] for t in braintasks._mem]
    assert "Una conversazione normale, non solo risposte dal cervello" in titoli
    assert "Il case study viene da Centioni, non da ATS" in titoli
    note19 = [t["note"] for t in braintasks._mem
              if t.get("idempotency_key") == "audit-2026-07-31-19"][0]
    assert note19.startswith("SOLO ANDREA")
    assert all(t["kind"] == "audit" for t in braintasks._mem)


def test_seed_ter_rilanciato_non_duplica_e_convive_con_gli_altri(post):
    mod1, mod2, mod3 = _carica_seed(), _carica_seed_bis(), _carica_seed_ter()
    mod1.seed(post); mod2.seed(post); mod3.seed(post)
    prima = len(braintasks._mem)
    mod3.seed(post)                          # rilancio del ter: zero duplicati
    assert len(braintasks._mem) == prima == 21   # 8 + 7 + 6
