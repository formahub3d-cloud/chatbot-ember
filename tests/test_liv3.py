"""V5 · Il livello 3 vive sul SERVER (tenant_flags), non in localStorage.

Prima: dv_liv3 nel browser — una riga di JavaScript e il guardrail spariva.
Ora: come `owner`, lo stato sta sul record lato server e il server APPLICA:
un'azione esterna (kind azione/agente in-approvazione) si accoda solo se il
tenant ha liv3 acceso. Default SPENTO, anche per i pannelli cliente.
"""
import pytest
from fastapi.testclient import TestClient

from app import main, braintasks, flags
from app.config import settings

TOK = "tok-di-test-lungo-abbastanza-123456"


@pytest.fixture()
def cl(monkeypatch):
    monkeypatch.setattr(settings, "admin_token", TOK)
    monkeypatch.setattr(braintasks, "_mem", [])
    flags.reset()
    return TestClient(main.app)


def _h():
    return {"Authorization": f"Bearer {TOK}"}


def test_default_spento_blocca_le_azioni_esterne(cl):
    r = cl.post("/admin/tasks", headers=_h(), json={
        "title": "Invia 3 solleciti", "kind": "azione", "scope": "ats",
        "status": "in-approvazione", "idempotency_key": "act-x"})
    assert r.status_code == 403
    assert "Livello 3 spento" in r.json()["detail"]
    assert braintasks._mem == []                     # NIENTE si è accodato


def test_acceso_si_accoda_ma_resta_in_approvazione(cl):
    r = cl.post("/admin/liv3", headers=_h(),
                json={"tenant": "ats", "on": True, "by": "andrea"})
    assert r.status_code == 200
    r2 = cl.post("/admin/tasks", headers=_h(), json={
        "title": "Invia 3 solleciti", "kind": "azione", "scope": "ats",
        "status": "in-approvazione", "idempotency_key": "act-y"})
    assert r2.status_code == 200
    # anche col livello 3 acceso, l'azione NASCE in approvazione: il freno
    # umano (Z2) non si scavalca mai
    assert r2.json()["task"]["status"] == "in-approvazione"


def test_get_riflette_lo_stato_e_il_default(cl):
    r = cl.get("/admin/liv3?tenant=ats", headers=_h())
    assert r.status_code == 200 and r.json()["liv3"] is False   # assente = spento
    cl.post("/admin/liv3", headers=_h(), json={"tenant": "ats", "on": True, "by": "andrea"})
    assert cl.get("/admin/liv3?tenant=ats", headers=_h()).json()["liv3"] is True
    # per-tenant: hrh resta spento
    assert cl.get("/admin/liv3?tenant=hrh", headers=_h()).json()["liv3"] is False


def test_decisione_umana_col_nome(cl):
    r = cl.post("/admin/liv3", headers=_h(), json={"tenant": "ats", "on": True, "by": ""})
    assert r.status_code == 422                      # senza nome non si decide
    assert cl.get("/admin/liv3", headers=_h()).status_code == 422   # senza tenant


def test_le_task_normali_non_sono_toccate(cl):
    """Il gate riguarda SOLO le azioni esterne: audit/gap/manuale passano."""
    for kind in ("audit", "gap", "manuale"):
        r = cl.post("/admin/tasks", headers=_h(), json={
            "title": f"t-{kind}", "kind": kind, "scope": "ats",
            "status": "aperta", "idempotency_key": f"k-{kind}"})
        assert r.status_code == 200
    # e un'azione che nasce 'aperta' (non richiesta di esecuzione) passa
    r = cl.post("/admin/tasks", headers=_h(), json={
        "title": "appunto", "kind": "agente", "scope": "ats", "status": "aperta",
        "idempotency_key": "k-app"})
    assert r.status_code == 200


# ── V5 · La rotazione delle chiavi: la logica pura del passo 4 ────────────────
def test_si_puo_revocare_solo_dopo_il_silenzio():
    import importlib.util, sys
    from pathlib import Path
    spec = importlib.util.spec_from_file_location(
        "rigenera", Path(__file__).resolve().parents[1] / "scripts" / "rigenera_chiavi.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["rigenera"] = mod
    spec.loader.exec_module(mod)
    # muta da 8 giorni → si può; da 2 → no; mai usata → si può; data rotta → freno
    assert mod.si_puo_revocare("2026-07-24", "2026-08-01") is True
    assert mod.si_puo_revocare("2026-07-30", "2026-08-01") is False
    assert mod.si_puo_revocare("", "2026-08-01") is True
    assert mod.si_puo_revocare("boh", "2026-08-01") is False
