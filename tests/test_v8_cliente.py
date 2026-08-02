"""V8/B · Il pannello del cliente — la terza persona del sistema.

Fino a ieri il cliente poteva PARLARE col proprio cervello e non poteva
GUARDARLO. Qui si prova che adesso può, e soprattutto che i tre divieti del
blocco B3 sono codice e non buone intenzioni: mai fuori dal proprio scope, mai
una scrittura diretta nel vault, mai le conversazioni dei propri utenti finali
senza che sia stato deciso.
"""
import pytest
from fastapi.testclient import TestClient

from app import brain, clientauth, clientkb, flags, main, metrics
from app.config import settings

client = TestClient(main.app)
ADM = {"Authorization": "Bearer " + "T" * 32}


@pytest.fixture(autouse=True)
def _pulizia(monkeypatch):
    clientauth._MEM.clear()
    clientkb.reset()
    flags.reset()
    metrics.reset()
    monkeypatch.setattr(settings, "client_session_secret", "s" * 32)
    monkeypatch.setattr(settings, "admin_token", "T" * 32)
    monkeypatch.setattr(settings, "database_url", "")
    yield
    clientauth._MEM.clear()
    clientkb.reset()
    flags.reset()


NOTE = [
    {"slug": "scheda-ats", "title": "Scheda cliente ATS", "path": "forma/clienti/ats/scheda-ats.md",
     "tenant": "ats", "updated_at": "2026-07-30T10:00:00", "tags": []},
    {"slug": "menu-ats", "title": "Menu e orari ATS", "path": "forma/clienti/ats/menu.md",
     "tenant": "ats", "updated_at": "2026-07-28T10:00:00", "tags": []},
    {"slug": "listino", "title": "Listino FORMA 2026", "path": "forma/listino.md",
     "tenant": "forma-core", "updated_at": "2026-08-01T10:00:00", "tags": []},
    {"slug": "scheda-centioni", "title": "Scheda Centioni", "path": "forma/clienti/centioni/x.md",
     "tenant": "centioni", "updated_at": "2026-08-01T10:00:00", "tags": []},
]


def _entra(monkeypatch, scopes=("ats",), email="anna@ats.it"):
    """Un cliente vero: account creato da FORMA, login, cookie di sessione."""
    t = {"name": "ATS", "tenant_code": "ats", "allowed_scopes": list(scopes),
         "allowed_origins": [], "branding": {}}
    monkeypatch.setattr(main.tenants, "get_tenant_by_key", lambda k: dict(t))
    clientauth.create(email, "Anna", "K-ATS", "password-lunga")
    r = client.post("/client/login", json={"email": email, "credential": "password-lunga"})
    assert r.status_code == 200
    return t


def _note_finte(monkeypatch):
    monkeypatch.setattr(brain, "enabled", lambda: True)
    monkeypatch.setattr(brain, "notes", lambda q="", limit=50: list(NOTE))


# ══════════════════════════════════════════════════════════════════════════
# B2.1 · «Ecco le cose che so di voi»
# ══════════════════════════════════════════════════════════════════════════
def test_il_cliente_vede_le_proprie_note_con_la_data(monkeypatch):
    _entra(monkeypatch)
    _note_finte(monkeypatch)
    d = client.get("/client/kb").json()
    assert d["totale"] == 2
    assert {n["slug"] for n in d["note"]} == {"scheda-ats", "menu-ats"}
    assert d["note"][0]["updated_at"]                 # «aggiornata quando»


def test_il_cliente_non_vede_le_note_di_un_altro_cliente(monkeypatch):
    """Il confine fra clienti è il prodotto. Se cade qui, non conta che regga
    nel retrieval."""
    _entra(monkeypatch)
    _note_finte(monkeypatch)
    slug = {n["slug"] for n in client.get("/client/kb").json()["note"]}
    assert "scheda-centioni" not in slug and "listino" not in slug


def test_una_chiave_master_non_apre_la_kb_di_tutti(monkeypatch):
    """`clientauth` già rifiuta la master alla creazione. Questo è il secondo
    freno: se ci arrivasse comunque, qui vale come nessuno scope."""
    _note_finte(monkeypatch)
    assert clientkb.kb(["*"])["totale"] == 0
    assert "nessuna area" in clientkb.kb([])["vuota_perche"]


def test_una_kb_vuota_dice_perche_e_vuota(monkeypatch):
    """Senza dato la spia dice «—» e dice QUALE dato manca: una pagina vuota
    muta farebbe credere «non sanno niente di noi» invece di «il motore non ha
    i metadati»."""
    _entra(monkeypatch)
    monkeypatch.setattr(brain, "enabled", lambda: False)
    monkeypatch.setattr(brain, "notes", lambda q="", limit=50: [])
    d = client.get("/client/kb").json()
    assert d["totale"] == 0 and "metadati" in d["vuota_perche"]


def test_senza_sessione_niente_pannello():
    for p in ("/client/kb", "/client/buchi"):
        assert client.get(p).status_code == 401
    assert client.post("/client/segnala", json={"cosa": "x"}).status_code == 401


# ══════════════════════════════════════════════════════════════════════════
# B2.2 · Segnalare, non correggere
# ══════════════════════════════════════════════════════════════════════════
def test_segnalare_mette_in_coda_e_non_tocca_il_vault(monkeypatch):
    _entra(monkeypatch)
    scritture = []
    monkeypatch.setattr(main.writeback, "save_note",
                        lambda *a, **k: scritture.append(a) or {"created": True})
    r = client.post("/client/segnala", json={"cosa": "Gli orari del sabato sono cambiati",
                                             "slug": "menu-ats", "titolo": "Menu e orari ATS"})
    assert r.status_code == 200
    assert scritture == []                       # ← il punto: NIENTE nel vault
    coda = client.get("/admin/segnalazioni", headers=ADM).json()
    assert coda["totale"] == 1
    s = coda["segnalazioni"][0]
    assert s["tenant"] == "ats" and s["stato"] == "aperta" and s["slug"] == "menu-ats"


def test_lo_scope_della_segnalazione_viene_dalla_sessione_non_dal_corpo(monkeypatch):
    """Non c'è nessun campo `tenant` da falsificare nel browser: se un giorno
    qualcuno lo aggiungesse, questo test lo troverebbe."""
    _entra(monkeypatch)
    client.post("/client/segnala", json={"cosa": "sbagliato", "tenant": "centioni"})
    assert clientkb.segnalazioni("centioni") == []
    assert len(clientkb.segnalazioni("ats")) == 1


def test_la_segnalazione_viene_redatta_non_scartata(monkeypatch):
    """A differenza delle proposte da conversazione qui si REDIGE: il cliente sta
    descrivendo un errore, e buttare via la segnalazione perché nomina un
    referente vuol dire non ascoltarlo."""
    _entra(monkeypatch)
    r = client.post("/client/segnala",
                    json={"cosa": "scrivete a vecchio@ats.it, l'indirizzo è cambiato"})
    assert r.status_code == 200
    testo = r.json()["segnalazione"]["cosa"]
    assert "vecchio@ats.it" not in testo and "indirizzo è cambiato" in testo


def test_l_owner_chiude_col_suo_nome_e_con_una_risposta(monkeypatch):
    _entra(monkeypatch)
    client.post("/client/segnala", json={"cosa": "gli orari sono cambiati"})
    sid = clientkb.segnalazioni("ats")[0]["id"]
    assert client.post("/admin/segnalazioni/chiudi", headers=ADM,
                       json={"id": sid, "stato": "accolta"}).status_code == 422   # senza nome
    r = client.post("/admin/segnalazioni/chiudi", headers=ADM,
                    json={"id": sid, "stato": "accolta", "by": "andrea",
                          "risposta": "corretto nella scheda"})
    assert r.status_code == 200
    chiuse = clientkb.segnalazioni("ats", stato="accolta")
    assert chiuse[0]["chiusa_da"] == "andrea" and chiuse[0]["risposta"]
    # e non si richiude due volte
    assert client.post("/admin/segnalazioni/chiudi", headers=ADM,
                       json={"id": sid, "stato": "respinta", "by": "andrea"}).status_code == 422


def test_la_coda_delle_segnalazioni_e_roba_da_admin():
    assert client.get("/admin/segnalazioni").status_code == 401
    assert client.post("/admin/segnalazioni/chiudi", json={"id": "x", "stato": "accolta",
                                                           "by": "y"}).status_code == 401


def test_un_cliente_non_puo_intasare_la_coda(monkeypatch):
    _entra(monkeypatch)
    for i in range(clientkb.MAX_APERTE):
        assert clientkb.segnala("ats", f"segnalazione numero {i}") is not None
    assert clientkb.segnala("ats", "una di troppo") is None


# ══════════════════════════════════════════════════════════════════════════
# B2.3 + B3 · I buchi: la pagina c'è, la decisione no — e lo dice
# ══════════════════════════════════════════════════════════════════════════
def test_i_buchi_sono_spenti_di_default_e_la_pagina_dice_perche(monkeypatch):
    """Il divieto di B3: «le conversazioni dei propri utenti finali senza che
    sia stato deciso». Una lista vuota muta direbbe «nessun buco», che è la cosa
    più sbagliata da far credere a un cliente il cui bot non sa rispondere."""
    _entra(monkeypatch)
    metrics.bump_gap(["ats"], "che orari fate il sabato?")
    d = client.get("/client/buchi").json()
    assert d["consentito"] is False and d["buchi"] == []
    assert "utenti finali" in d["perche"] and "decidiamo insieme" in d["perche"]


def test_con_la_spunta_accesa_i_buchi_si_vedono_ma_solo_i_propri(monkeypatch):
    _entra(monkeypatch)
    flags.set_buchi("ats", True, "andrea")
    metrics.bump_gap(["ats"], "che orari fate il sabato?")
    metrics.bump_gap(["centioni"], "quanto costa il CRM?")
    d = client.get("/client/buchi").json()
    assert d["consentito"] is True
    domande = [g["q"] for g in d["buchi"]]
    assert "che orari fate il sabato?" in domande
    assert all("CRM" not in q for q in domande)


def test_la_spunta_dei_buchi_e_server_side_e_si_firma(monkeypatch):
    """Stessa famiglia di `liv3` e `libera`: sta sul record, non nella
    richiesta, e la accende una persona col suo nome."""
    assert flags.buchi("ats") is False
    assert flags.set_buchi("ats", True, "") is False        # senza nome, niente
    assert client.post("/admin/buchi-cliente", headers=ADM,
                       json={"tenant": "ats", "on": True, "by": "andrea"}).status_code == 200
    assert client.get("/admin/buchi-cliente?tenant=ats", headers=ADM).json()["buchi"] is True
    assert client.post("/admin/buchi-cliente", json={"tenant": "ats", "on": True,
                                                     "by": "x"}).status_code == 401


def test_accendere_i_buchi_non_spegne_gli_altri_flag():
    """Il difetto già trovato una volta con `libera`/`liv3`: l'assegnazione
    secca sul fallback in memoria spegneva il vicino."""
    flags.set_liv3("ats", True, "andrea")
    flags.set_buchi("ats", True, "andrea")
    assert flags.liv3("ats") is True and flags.buchi("ats") is True
