"""S5.1c/2 · Le chiavi che il registro non riesce a leggere.

Il controllo nasce da una domanda semplice: **cosa succede se una chiave ha uno
scope diverso dal proprio `tenant_code`?** Il registro filtra per il codice, la
RLS per gli scope, quindi la SELECT del saldo torna vuota — e il freno, che a
saldo vuoto e senza accrediti dice «mai aperto», lascia passare tutto.

Fallisce nella direzione giusta, ma in silenzio. Questi test tengono fermo che
il silenzio sia finito: il caso si vede all'avvio e in `/admin/status`, con il
NOME della chiave, perché «una chiave incoerente» senza sapere quale non si
ripara.
"""
import pytest
from fastapi.testclient import TestClient

from app import coerenza, main, manage_apikeys, tenants
from app.config import settings

client = TestClient(main.app)


def _chiave(nome, scope, codice=None, active=True):
    branding = {"tenant_code": codice} if codice is not None else {}
    return {"name": nome, "active": active, "tenants": scope,
            "branding_full": branding}


# ── esamina: la diagnosi, senza database ────────────────────────────────────

def test_una_chiave_normale_e_coerente():
    d = coerenza.esamina([_chiave("ATS", ["ats"], "ats")])
    assert d["stato"] == coerenza.OK
    assert d["fuori_scope"] == [] and d["senza_codice"] == []


def test_il_codice_puo_stare_fra_PIU_scope():
    """La dogfood ha `forma-core` e `andrea`: il codice è uno dei due, ed è
    giusto così."""
    d = coerenza.esamina([_chiave("FORMA", ["forma-core", "andrea"], "forma-core")])
    assert d["stato"] == coerenza.OK


def test_il_codice_FUORI_dai_propri_scope_si_vede_col_nome():
    """È il caso che rende cieco il registro: la RLS nasconde le righe di
    `altro`, il saldo torna vuoto e il freno passa tutto."""
    d = coerenza.esamina([_chiave("Ditta", ["ats"], "altro")])
    assert d["stato"] == coerenza.GUASTO
    assert d["fuori_scope"] == [{"chiave": "Ditta", "tenant_code": "altro",
                                 "scope": ["ats"]}]


def test_una_chiave_SENZA_codice_e_un_difetto_diverso():
    """Qui il consumo non si scrive proprio (`codice_tenant` non indovina dagli
    scope): il cliente usa il prodotto e non paga niente. Conseguenza diversa,
    elenco diverso."""
    d = coerenza.esamina([_chiave("Vecchia", ["ats"])])
    assert d["stato"] == coerenza.GUASTO
    assert d["senza_codice"] == [{"chiave": "Vecchia", "scope": ["ats"]}]
    assert d["fuori_scope"] == []


def test_la_chiave_master_non_e_un_cliente():
    """`*` è l'accesso admin server-side: non ha un tenant e non deve averlo.
    Segnalarla vorrebbe dire un allarme sempre acceso, cioè un allarme spento."""
    assert coerenza.esamina([_chiave("master", ["*"])])["stato"] == coerenza.OK


def test_una_chiave_revocata_non_si_conta():
    """Non consuma: tenerla nell'elenco riempirebbe l'avviso di roba morta."""
    assert coerenza.esamina([_chiave("vecchia", ["ats"], active=False)])["stato"] \
        == coerenza.OK


def test_gli_scope_si_leggono_anche_se_arrivano_come_testo():
    """La colonna può tornare come array Postgres serializzato: se il parsing
    fallisse, ogni chiave sembrerebbe fuori scope — un allarme che grida sempre
    è peggio di nessun allarme."""
    d = coerenza.esamina([{"name": "ATS", "active": True, "tenants": "{ats,altro}",
                           "branding_full": {"tenant_code": "ats"}}])
    assert d["stato"] == coerenza.OK


# ── stato(): i tre esiti, mai confusi ───────────────────────────────────────

def test_senza_elenco_chiavi_dice_NON_SO(monkeypatch):
    """Non «tutto a posto»: è il difetto del V10 — l'allarme che dopo un
    redeploy si spegne da solo e dice che va tutto bene."""
    monkeypatch.setattr(tenants, "_apikeys_enabled", lambda: False)
    assert coerenza.stato()["stato"] == coerenza.NON_SO


def test_se_la_lettura_esplode_dice_NON_SO(monkeypatch):
    monkeypatch.setattr(tenants, "_apikeys_enabled", lambda: True)
    monkeypatch.setattr(manage_apikeys, "list_keys",
                        lambda: (_ for _ in ()).throw(RuntimeError("giù")))
    d = coerenza.stato()
    assert d["stato"] == coerenza.NON_SO and "RuntimeError" in d["motivo"]


# ── la riga d'avvio ─────────────────────────────────────────────────────────

def test_la_riga_di_avvio_nomina_le_chiavi_e_la_conseguenza(monkeypatch):
    monkeypatch.setattr(tenants, "_apikeys_enabled", lambda: True)
    monkeypatch.setattr(manage_apikeys, "list_keys",
                        lambda: [_chiave("Ditta", ["ats"], "altro")])
    riga = coerenza.riga_boot()
    assert "Ditta" in riga and "altro" in riga
    assert "freno che passa tutto" in riga, "senza la conseguenza è solo un codice"


def test_quando_va_bene_la_riga_lo_dice_senza_allarmare(monkeypatch):
    monkeypatch.setattr(tenants, "_apikeys_enabled", lambda: True)
    monkeypatch.setattr(manage_apikeys, "list_keys",
                        lambda: [_chiave("ATS", ["ats"], "ats")])
    assert "→" not in coerenza.riga_boot()      # la freccia marca il guasto


# ── /admin/status ───────────────────────────────────────────────────────────

def test_lo_stato_arriva_in_admin_status(monkeypatch):
    monkeypatch.setattr(settings, "admin_token", "T0ken-forte-di-prova")
    monkeypatch.setattr(tenants, "_apikeys_enabled", lambda: True)
    monkeypatch.setattr(manage_apikeys, "list_keys",
                        lambda: [_chiave("Ditta", ["ats"], "altro")])
    r = client.get("/admin/status",
                   headers={"Authorization": "Bearer T0ken-forte-di-prova"})
    assert r.status_code == 200
    d = r.json()["chiavi_registro"]
    assert d["stato"] == "guasto"
    assert d["fuori_scope"][0]["chiave"] == "Ditta"


def test_admin_status_regge_il_database_irraggiungibile(monkeypatch):
    """`/admin/status` è la pagina che si apre QUANDO qualcosa non va: se un
    controllo la fa esplodere, sparisce proprio nel momento in cui serve.

    Il guasto simulato è quello VERO — Supabase configurato ma giù, quindi
    `list_keys()` che solleva. La prima versione di questo test faceva esplodere
    `_apikeys_enabled()`, che legge due settings e non può fallire: un test su
    uno scenario impossibile che, per giunta, andava rosso per un motivo
    diverso da quello che pretendeva di provare."""
    monkeypatch.setattr(settings, "admin_token", "T0ken-forte-di-prova")
    monkeypatch.setattr(tenants, "_apikeys_enabled", lambda: True)
    monkeypatch.setattr(manage_apikeys, "list_keys",
                        lambda: (_ for _ in ()).throw(RuntimeError("database giù")))
    r = client.get("/admin/status",
                   headers={"Authorization": "Bearer T0ken-forte-di-prova"})
    assert r.status_code == 200
    assert r.json()["chiavi_registro"]["stato"] == "non-so"
