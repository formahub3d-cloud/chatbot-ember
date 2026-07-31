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
