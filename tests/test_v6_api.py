"""V6 · Gli endpoint nuovi e il seed delle task, contro l'app vera (TestClient).

Non è un doppione dei test di unità: qui si prova il PERIMETRO — chi può
chiamare cosa, e cosa risponde il server quando qualcuno prova a scavalcarlo.
"""
import importlib.util
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import braintasks, flags, learned, main, proposals
from app.config import settings

ROOT = Path(__file__).resolve().parents[1]
TOK = "tok-di-test-lungo-abbastanza-123456"
AUTH = {"Authorization": f"Bearer {TOK}"}


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(settings, "admin_token", TOK)
    monkeypatch.setattr(braintasks, "_mem", [])
    flags.reset()
    proposals.reset()
    yield TestClient(main.app)
    flags.reset()
    proposals.reset()


# ── B2 · La spunta «conoscenza generale», sul server ────────────────────────

def test_libera_default_spento_e_si_accende_solo_firmata(client):
    assert client.get("/admin/libera?tenant=ats", headers=AUTH).json()["libera"] is False
    r = client.post("/admin/libera", json={"tenant": "ats", "on": True, "by": ""}, headers=AUTH)
    assert r.status_code == 422                              # senza firma non si tocca
    r = client.post("/admin/libera", json={"tenant": "ats", "on": True, "by": "Andrea"}, headers=AUTH)
    assert r.status_code == 200 and r.json()["libera"] is True
    assert client.get("/admin/libera?tenant=ats", headers=AUTH).json()["libera"] is True


def test_libera_e_solo_admin(client):
    assert client.get("/admin/libera?tenant=ats").status_code == 401
    assert client.post("/admin/libera", json={"tenant": "ats", "on": True, "by": "x"}).status_code == 401


def test_liv3_e_libera_non_si_pestano_i_piedi(client):
    client.post("/admin/liv3", json={"tenant": "ats", "on": True, "by": "Andrea"}, headers=AUTH)
    client.post("/admin/libera", json={"tenant": "ats", "on": True, "by": "Andrea"}, headers=AUTH)
    assert client.get("/admin/liv3?tenant=ats", headers=AUTH).json()["liv3"] is True
    assert client.get("/admin/libera?tenant=ats", headers=AUTH).json()["libera"] is True


def test_chi_puo_uscire_dal_vault(monkeypatch):
    """La decisione sta QUI, server-side: owner per costruzione, tenant solo
    con la spunta sul suo record. Mai un campo della richiesta."""
    flags.reset()
    assert main._puo_uscire_dal_vault({"branding": {"owner": True}}) is True
    cliente = {"name": "ATS", "branding": {"tenant_code": "ats"}, "allowed_scopes": ["ats"]}
    assert main._puo_uscire_dal_vault(cliente) is False
    flags.set_libera("ats", True, "Andrea")
    assert main._puo_uscire_dal_vault(cliente) is True
    flags.reset()


# ── B3 · «Cosa abbiamo imparato»: proposte, non note ────────────────────────

def test_imparato_richiede_admin_e_scope(client):
    assert client.post("/admin/conversazione/imparato", json={"scope": "ats"}).status_code == 401
    r = client.post("/admin/conversazione/imparato", json={"history": [], "scope": ""}, headers=AUTH)
    assert r.status_code == 422


def test_imparato_accoda_e_non_scrive(client, monkeypatch):
    monkeypatch.setattr(learned, "chat", lambda s, u: '{"imparato":[{"titolo":"Ritiro in centro",'
                        '"contenuto":"Solo centro citta.","citazione":"fuori dal centro non lo facciamo"}]}')
    r = client.post("/admin/conversazione/imparato", headers=AUTH, json={
        "scope": "ats", "conversazione": "chat console",
        "history": [{"role": "user", "content": "ritirate a domicilio fuori citta?"},
                    {"role": "assistant", "content": "fuori dal centro non lo facciamo"}]})
    assert r.status_code == 200
    body = r.json()
    assert body["proposte"] == 1 and body["imparato"][0]["source"] == "conversazione"
    assert body["imparato"][0]["citazione"]
    assert "solo se le approvi" in body["nota"]
    # ed è in coda, dove si decide — non nel vault
    assert any(p["source"] == "conversazione" for p in
               client.get("/admin/proposals", headers=AUTH).json()["proposals"])


def test_imparato_senza_niente_da_imparare_e_un_esito_normale(client, monkeypatch):
    monkeypatch.setattr(learned, "chat", lambda s, u: '{"imparato": []}')
    r = client.post("/admin/conversazione/imparato", headers=AUTH, json={
        "scope": "ats", "history": [{"role": "user", "content": "ciao come va"},
                                    {"role": "assistant", "content": "bene, dimmi pure"}]})
    assert r.status_code == 200 and r.json()["proposte"] == 0


# ── Le task del V6 come dati ────────────────────────────────────────────────

def _carica_seed_v6():
    spec = importlib.util.spec_from_file_location(
        "seed_v6", ROOT / "scripts" / "seed_task_v6_2026_08_01.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["seed_v6"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def post(client):
    def _post(path, body):
        r = client.post(path, json=body, headers=AUTH)
        assert r.status_code == 200, f"{path}: {r.status_code} {r.text[:200]}"
        return r.json()
    return _post


def test_seed_v6_crea_le_undici_task_con_la_loro_priorita(post):
    mod = _carica_seed_v6()
    esiti = mod.seed(post)
    assert len(esiti) == 11
    assert [e["key"] for e in esiti] == [f"audit-2026-08-01-{n}" for n in range(22, 33)]
    assert all(e["status"] == "aperta" for e in esiti)
    prio = {e["key"]: e["priorita"] for e in esiti}
    assert prio["audit-2026-08-01-22"] == "alta"     # il muro diventa una porta
    assert prio["audit-2026-08-01-28"] == "alta"     # l'orbita protagonista
    assert prio["audit-2026-08-01-30"] == "alta"     # il colore non basta da solo
    assert prio["audit-2026-08-01-24"] == "media"
    assert sum(1 for v in prio.values() if v == "alta") == 5
    assert all(t["kind"] == "audit" for t in braintasks._mem)


def test_seed_v6_rilanciato_non_duplica(post):
    mod = _carica_seed_v6()
    mod.seed(post)
    prima = len(braintasks._mem)
    mod.seed(post)
    assert len(braintasks._mem) == prima == 11


def test_la_31_dichiara_di_essere_la_stessa_della_20():
    """La sovrapposizione con `audit-2026-07-31-20` è dichiarata nella nota:
    due task per lo stesso lavoro sono un difetto se nessuno lo sa."""
    mod = _carica_seed_v6()
    nota = [n for k, _t, _p, n in mod.TASK_V6 if k == "audit-2026-08-01-31"][0]
    assert "audit-2026-07-31-20" in nota
