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


# ── V5c (revisione 1/08 notte) · La porta di servizio è chiusa ────────────────
def test_la_porta_di_servizio_e_chiusa(cl):
    """La sequenza della revisione: nascere 'aperta' (nessun gate) e poi
    transitare a 'in-approvazione' NON aggira più il freno — la promessa del
    pannello («da spento non si accodano nemmeno») ora è mantenuta ovunque."""
    r = cl.post("/admin/tasks", headers=_h(), json={
        "title": "Invia 3 solleciti", "kind": "azione", "scope": "ats",
        "status": "aperta", "idempotency_key": "act-porta"})
    assert r.status_code == 200                      # nascere 'aperta' è lecito
    tid = r.json()["task"]["id"]
    r2 = cl.post("/admin/tasks/transition", headers=_h(),
                 json={"id": tid, "to": "in-approvazione"})
    assert r2.status_code == 403
    assert "Livello 3 spento" in r2.json()["detail"]
    assert braintasks._mem[0]["status"] == "aperta"  # ferma dov'era, mai in coda
    # col livello 3 acceso la STESSA transizione passa
    cl.post("/admin/liv3", headers=_h(), json={"tenant": "ats", "on": True, "by": "andrea"})
    r3 = cl.post("/admin/tasks/transition", headers=_h(),
                 json={"id": tid, "to": "in-approvazione"})
    assert r3.status_code == 200
    assert braintasks._mem[0]["status"] == "in-approvazione"


def test_le_audit_transitano_anche_a_freno_tirato(cl):
    """Il percorso di close_audit_2026_08_01 (task 11 e 16, kind='audit' →
    in-approvazione) NON deve incocciare nel guardrail: il freno è per le
    azioni esterne, non per il registro dei lavori."""
    r = cl.post("/admin/tasks", headers=_h(), json={
        "title": "Le schede clienti hanno due note a testa", "kind": "audit",
        "scope": "", "status": "aperta", "idempotency_key": "audit-2026-07-31-11"})
    tid = r.json()["task"]["id"]
    r2 = cl.post("/admin/tasks/transition", headers=_h(),
                 json={"id": tid, "to": "in-approvazione", "note": "IN CORSO"})
    assert r2.status_code == 200                     # liv3 spento, ma passa: è audit

