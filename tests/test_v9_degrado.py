"""V9/A · Una funzione spenta lo dice DOVE si usa.

Il difetto, visto in produzione il 2/08: la pagina «Cosa so di te» diceva «Non so
ancora niente di te» mentre la verità era «non posso ricordare niente, mi manca
la tabella». `/admin/status` lo sapeva; la schermata no. Una funzione spenta che
sembra una funzione inutile non chiede di essere riparata.
"""
import pytest
from fastapi.testclient import TestClient

from app import dbcheck, degrado, main
from app.config import settings

TOK = "tok-di-test-lungo-abbastanza-123456"
AUTH = {"Authorization": f"Bearer {TOK}"}


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(settings, "admin_token", TOK)
    return TestClient(main.app)


def _db(monkeypatch, mancanti=()):
    """Un database che c'è, con esattamente queste attese non soddisfatte."""
    monkeypatch.setattr(settings, "grants_backend", "supabase")
    monkeypatch.setattr(settings, "database_url", "postgres://x/y")
    tabelle = {t for t, c, _d, _r in dbcheck.ATTESE if (t, c) not in mancanti}
    colonne = {(t, c) for t, c, _d, _r in dbcheck.ATTESE
               if c and not c.startswith("@check:") and (t, c) not in mancanti}
    check = {(t, "@check:CHECK (status = ANY (ARRAY['da-verificare'::text]))")
             for t, c, _d, _r in dbcheck.ATTESE if c and c.startswith("@check:")}
    # una tabella resta "presente" anche se le manca una colonna
    tabelle |= {t for t, c, _d, _r in dbcheck.ATTESE if c and (t, c) in mancanti}
    monkeypatch.setattr(dbcheck, "_trovate", lambda: (tabelle, colonne | check))


# ══════════════════════════════════════════════════════════════════════════
# Tre esiti, mai due
# ══════════════════════════════════════════════════════════════════════════
def test_tutto_a_posto_non_mostra_niente(monkeypatch):
    """Un avviso che compare sempre smette di essere un avviso."""
    _db(monkeypatch)
    monkeypatch.setattr(settings, "elevenlabs_voice_id_dante", "x")
    monkeypatch.setattr(settings, "elevenlabs_voice_id_virgilio", "x")
    monkeypatch.setattr(settings, "elevenlabs_voice_id_beatrice", "x")
    assert degrado.per("memoria")["stato"] == "acceso"
    assert degrado.per("voci-agente")["stato"] == "acceso"
    assert degrado.per("memoria")["perche"] == ""


def test_la_tabella_mancante_diventa_una_frase_per_chi_guarda(monkeypatch):
    """IL caso del 2/08. La frase non nomina la tabella al posto del problema:
    dice cosa smette di funzionare, e la riga tecnica sta a parte."""
    _db(monkeypatch, mancanti={("tenant_memory", None)})
    d = degrado.per("memoria")
    assert d["stato"] == "spento"
    assert "si azzera" in d["perche"] or "redeploy" in d["perche"]
    assert "tenant_memory" in d["manca"]
    assert "db/tenant_memory.sql" in d["come"]
    assert d["dove"]                       # dove si vede, non solo cosa manca


def test_schema_illeggibile_e_un_terzo_esito(monkeypatch):
    """«Non ho potuto guardare» non è «acceso» e non è «spento»: dirlo come uno
    dei due è il modo esatto in cui nasce un pannello che mente."""
    monkeypatch.setattr(settings, "grants_backend", "supabase")
    monkeypatch.setattr(settings, "database_url", "postgres://x/y")
    monkeypatch.setattr(dbcheck, "_trovate",
                        lambda: (_ for _ in ()).throw(OSError("pooler giù")))
    d = degrado.per("memoria")
    assert d["stato"] == "non-so"
    assert "non è leggibile" in d["perche"] and d["manca"] == []


def test_senza_database_e_una_configurazione_non_un_guasto(monkeypatch):
    monkeypatch.setattr(settings, "grants_backend", "static")
    d = degrado.per("memoria")
    assert d["stato"] == "spento" and d["manca"] == ["database"]
    assert "riavvio" in d["perche"] and "DATABASE_URL" in d["come"]


def test_una_variabile_mancante_vale_come_una_tabella(monkeypatch):
    """La regola è generale: tabella, variabile o chiave — la forma è una sola."""
    monkeypatch.setattr(settings, "elevenlabs_voice_id_dante", "")
    monkeypatch.setattr(settings, "elevenlabs_voice_id_virgilio", "V")
    monkeypatch.setattr(settings, "elevenlabs_voice_id_beatrice", "B")
    d = degrado.per("voci-agente")
    assert d["stato"] == "spento" and d["manca"] == ["ELEVENLABS_VOICE_ID_DANTE"]
    assert d["perche"].startswith("Dante parla")
    assert d["come"] == "Imposta ELEVENLABS_VOICE_ID_DANTE."


def test_tre_ragioni_uguali_diventano_una_frase_sola(monkeypatch):
    """«Dante parla con la voce di Divina, Virgilio parla con la voce di Divina
    e Beatrice parla…» è tecnicamente giusto e nessuno lo legge fino in fondo."""
    for a in ("dante", "virgilio", "beatrice"):
        monkeypatch.setattr(settings, f"elevenlabs_voice_id_{a}", "")
    d = degrado.per("voci-agente")
    assert d["perche"].count("voce di Divina") == 1
    assert "Dante, Virgilio e Beatrice" in d["perche"]
    assert d["come"].startswith("Imposta ") and d["come"].count("Imposta") == 1


def test_una_funzione_sconosciuta_non_inventa_un_allarme():
    assert degrado.per("mai-registrata")["stato"] == "acceso"


# ══════════════════════════════════════════════════════════════════════════
# Il registro: ogni voce ha un posto dove si vede
# ══════════════════════════════════════════════════════════════════════════
def test_ogni_funzione_dichiara_dove_si_vede():
    """È la regola nuova del giro. Una funzione registrata qui e mostrata da
    nessuna parte sarebbe di nuovo il difetto del 2/08, con un modulo in più."""
    assert len(degrado.FUNZIONI) >= 5
    for nome, f in degrado.FUNZIONI.items():
        assert f["titolo"] and f["dove"], nome
        assert f["serve"], nome


def test_le_tabelle_citate_esistono_fra_le_attese_di_dbcheck():
    """La frase «cosa smette di funzionare» si legge da dbcheck: due copie della
    stessa frase divergono, e quella sbagliata è sempre quella che legge l'utente."""
    attese = {(t, c) for t, c, _d, _r in dbcheck.ATTESE}
    for nome, f in degrado.FUNZIONI.items():
        for d in f["serve"]:
            if d["tipo"] == "tabella":
                assert (d["tabella"], d["colonna"]) in attese, f"{nome} → {d}"


def test_i_campi_env_citati_esistono_davvero_in_settings():
    """Un campo scritto male darebbe «spento» per sempre, in silenzio."""
    for nome, f in degrado.FUNZIONI.items():
        for d in f["serve"]:
            if d["tipo"] == "env":
                assert hasattr(settings, d["campo"]), f"{nome} → {d['campo']}"


# ══════════════════════════════════════════════════════════════════════════
# Dove si vede: le schermate lo portano con sé
# ══════════════════════════════════════════════════════════════════════════
def test_la_pagina_della_memoria_porta_il_suo_degrado(client, monkeypatch):
    _db(monkeypatch, mancanti={("tenant_memory", None)})
    d = client.get("/admin/memoria?tenant=ats", headers=AUTH).json()
    assert d["degrado"]["stato"] == "spento"
    assert "tenant_memory" in d["degrado"]["manca"]


def test_lo_stato_elenca_tutte_le_funzioni(client, monkeypatch):
    _db(monkeypatch)
    f = client.get("/admin/status", headers=AUTH).json()["funzioni"]
    assert set(f) == set(degrado.FUNZIONI)
    assert all("stato" in v for v in f.values())


def test_spente_e_solo_quelle_che_valgono_un_avviso(monkeypatch):
    _db(monkeypatch, mancanti={("tenant_memory", None)})
    for a in ("dante", "virgilio", "beatrice"):
        monkeypatch.setattr(settings, f"elevenlabs_voice_id_{a}", "x")
    monkeypatch.setattr(settings, "tavily_api_key", "t")
    nomi = {s["funzione"] for s in degrado.spente()}
    assert "memoria" in nomi and "voci-agente" not in nomi
