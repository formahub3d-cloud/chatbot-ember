"""X1 · La chiusura delle cinque task audit FATTE: per chiave, mai per id.

Il close script gira qui contro l'app vera (TestClient, fallback in-memory):
stessa logica della produzione, zero rete. Si prova la strada intera della
macchina a stati (la 01 e la 09 nascono in-approvazione: servono tre passi),
la nota di chiusura che si AGGIUNGE senza cancellare quella di nascita, e
l'idempotenza (rilanciare dice «già chiusa», non riapre e non duplica).
"""
import importlib.util
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import main, braintasks
from app.config import settings

ROOT = Path(__file__).resolve().parents[1]


def _carica(nome, file):
    spec = importlib.util.spec_from_file_location(nome, ROOT / "scripts" / file)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[nome] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def post(monkeypatch):
    monkeypatch.setattr(settings, "admin_token", "tok-di-test-lungo-abbastanza-123456")
    monkeypatch.setattr(braintasks, "_mem", [])
    client = TestClient(main.app)

    def _post(path, body):
        r = client.post(path, json=body,
                        headers={"Authorization": "Bearer tok-di-test-lungo-abbastanza-123456"})
        assert r.status_code == 200, f"{path}: {r.status_code} {r.text[:200]}"
        return r.json()
    return _post


def _per_chiave():
    return {t.get("idempotency_key"): t for t in braintasks._mem}


def test_chiude_le_cinque_e_lascia_le_altre(post):
    """Scenario di produzione: i tre seed sono girati, poi arriva la chiusura.
    Le 5 diventano 'fatta' (con firma e nota di chiusura APPESA), le altre 16
    restano esattamente com'erano."""
    _carica("seed_audit", "seed_audit_2026_07_31.py").seed(post)
    _carica("seed_audit_bis", "seed_audit_2026_07_31_bis.py").seed(post)
    _carica("seed_audit_ter", "seed_audit_2026_07_31_ter.py").seed(post)
    chiuse = _carica("close_audit", "close_audit_2026_07_31.py").chiudi(post)

    assert [e["esito"] for e in chiuse] == ["chiusa"] * 5
    per = _per_chiave()
    fatte = {"audit-2026-07-31-01", "audit-2026-07-31-02", "audit-2026-07-31-03",
             "audit-2026-07-31-09", "audit-2026-07-31-10"}
    for k in fatte:
        assert per[k]["status"] == "fatta"
        assert per[k]["closed_by"] == "andrea"          # la decisione è firmata
        assert "FATTA ·" in per[k]["note"]              # nota di chiusura presente
    # la nota di nascita NON è stata cancellata (append, non replace)
    assert per["audit-2026-07-31-09"]["note"].startswith("Le finestre «cieca»")
    # la 10 porta il numero VERO di produzione, con la morale sulla misura in lab
    assert "1265 ms" in per["audit-2026-07-31-10"]["note"]
    assert "78" in per["audit-2026-07-31-10"]["note"]
    # le altre restano aperte, non toccate
    for n in (4, 5, 6, 7, 8, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21):
        k = f"audit-2026-07-31-{n:02d}"
        assert per[k]["status"] == "aperta", k
    assert len(braintasks._mem) == 21                   # 8 + 7 + 6, zero doppioni


def test_rilancio_dice_gia_chiusa_e_non_riapre(post):
    _carica("seed_audit", "seed_audit_2026_07_31.py").seed(post)
    _carica("seed_audit_bis", "seed_audit_2026_07_31_bis.py").seed(post)
    close = _carica("close_audit", "close_audit_2026_07_31.py")
    close.chiudi(post)
    prima = len(braintasks._mem)
    esiti = close.chiudi(post)                          # secondo giro
    assert [e["esito"] for e in esiti] == ["già chiusa"] * 5
    assert len(braintasks._mem) == prima
    nota10 = _per_chiave()["audit-2026-07-31-10"]["note"]
    assert nota10.count("1265 ms") == 1                 # la nota non si accumula


def test_ambiente_vergine_crea_e_chiude(post):
    """Senza seed (ambiente nuovo): la task mancante nasce col titolo verbatim
    e viene chiusa — lo stato finale è corretto comunque."""
    esiti = _carica("close_audit", "close_audit_2026_07_31.py").chiudi(post)
    assert [e["esito"] for e in esiti] == ["chiusa"] * 5
    per = _per_chiave()
    assert len(braintasks._mem) == 5
    assert per["audit-2026-07-31-03"]["title"] == (
        "Traduci le quarantadue skill in italiano, e chiamale col lavoro che fanno")
    assert all(t["status"] == "fatta" for t in braintasks._mem)


def test_transition_con_nota_appende(post):
    """La capacità nuova dell'API: /admin/tasks/transition accetta `note` e la
    AGGIUNGE alla nota esistente (mai sostituire — la storia resta)."""
    r = post("/admin/tasks", {"kind": "audit", "title": "Prova nota",
                              "note": "nota di nascita", "status": "aperta",
                              "idempotency_key": "prova-nota-append"})
    tid = r["task"]["id"]
    post("/admin/tasks/transition", {"id": tid, "to": "fatta", "by": "andrea",
                                     "note": "nota di chiusura"})
    t = _per_chiave()["prova-nota-append"]
    assert t["note"] == "nota di nascita\nnota di chiusura"
    assert t["status"] == "fatta" and t["closed_by"] == "andrea"
