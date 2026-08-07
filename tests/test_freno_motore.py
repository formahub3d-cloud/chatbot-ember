"""S5.1c/2 · Il freno nel motore: la decisione, la memoria, il muro.

La decisione è gemella di quella dell'orchestratore e i test stanno da
entrambe le parti apposta: se un giorno divergessero, lo stesso cliente
verrebbe fermato in un servizio e servito nell'altro.

Qui in più ci sono le due cose che nascono dalla chat:

  · **il saldo si tiene in mente per un minuto**, perché una connessione nuova
    prima di ogni risposta si sente davanti alla prima sillaba — e ogni
    addebito lo scala di quello che ha appena consumato, così fra due letture
    il conto resta esatto;
  · **il rifiuto non si tiene MAI in mente**: chi compra un pacchetto adesso
    deve poter scrivere il messaggio dopo, non fra un minuto.
"""
import time
from datetime import date, datetime, timezone

import pytest

from app import freno, ledger, main, rag, tariffa, tenants, uso
from app.config import settings
from fastapi.testclient import TestClient

client = TestClient(main.app)

TENANT = {"name": "ATS", "allowed_scopes": ["ats"], "allowed_origins": [],
          "branding": {"tenant_code": "ats"}, "quota_day": 0}
VUOTO = {"mensile": 0, "extra": 0, "regalo": 0}


@pytest.fixture(autouse=True)
def _pulisci():
    freno.dimentica()
    yield
    freno.dimentica()


# ── la decisione: le stesse regole dell'orchestratore ────────────────────────

def test_col_credito_si_passa():
    assert freno.decidi({"mensile": 900}, operazione="chat").blocca is False


def test_a_zero_ci_si_ferma():
    d = freno.decidi(VUOTO, operazione="chat")
    assert d.blocca is True and d.motivo == "credito-esaurito"


def test_un_saldo_non_letto_non_e_un_saldo_a_zero():
    d = freno.decidi(None, operazione="chat")
    assert d.esito == freno.NON_SO and d.blocca is False and d.residuo is None


def test_a_zero_senza_aver_mai_ricevuto_niente_non_e_esaurito():
    d = freno.decidi(VUOTO, operazione="chat", mai_visto=True)
    assert d.blocca is False and d.motivo == "senza-dotazione"


def test_la_voce_e_inclusa_e_passa_lo_stesso():
    assert freno.decidi(VUOTO, operazione="voce").blocca is False


def test_un_operazione_senza_tariffa_solleva():
    with pytest.raises(tariffa.OperazioneSconosciuta):
        freno.decidi({"mensile": 9}, operazione="teletrasporto")


def test_il_rinnovo_e_il_primo_del_mese_dopo():
    assert freno.rinnovo_il(datetime(2026, 12, 9, tzinfo=timezone.utc)) == date(2027, 1, 1)


def test_le_due_decisioni_sono_la_stessa_decisione():
    """Se un giorno divergessero, lo stesso cliente pagherebbe in due modi a
    seconda di quale servizio ha risposto. Qui si confronta ciò che il motore
    può confrontare da solo: la riga dell'avviso e i tre esiti."""
    assert freno.QUASI_FINITO == 400_000
    assert (freno.PASSA, freno.FERMO, freno.NON_SO) == ("passa", "fermo", "non-so")


# ── la frase: la legge anche uno sconosciuto ────────────────────────────────

def test_il_muro_porta_una_frase_discreta():
    """Dal widget di un cliente chi scrive non è il cliente: è il cliente del
    cliente. «Aggiungi un pacchetto» davanti a quella persona è un invito a chi
    non può comprare e un fatto sui conti di un'azienda detto ai suoi
    visitatori."""
    fuori = freno.decidi(VUOTO, operazione="chat").come_dizionario()
    frase = fuori["frase"].lower()
    assert "non è colpa tua" in frase
    for parola in ("token", "pacchetto", "credito", "paga", "abbonamento"):
        assert parola not in frase, f"«{parola}» non si dice a uno sconosciuto"


def test_quando_si_passa_non_c_e_nessuna_frase():
    assert "frase" not in freno.decidi({"mensile": 9}, operazione="chat").come_dizionario()


# ── la memoria: una connessione in meno davanti alla prima sillaba ──────────

def _finge_lettura(monkeypatch, saldi, conta=None):
    def _leggi(codice, tenant):
        if conta is not None:
            conta.append(codice)
        return (dict(saldi) if saldi is not None else None,
                False if saldi else True)
    monkeypatch.setattr(freno, "_leggi", _leggi)
    monkeypatch.setattr(ledger, "attivo", lambda: True)


def test_il_saldo_positivo_si_legge_una_volta_sola(monkeypatch):
    letture = []
    _finge_lettura(monkeypatch, {"mensile": 500_000}, letture)
    for _ in range(3):
        assert freno.controlla(TENANT, "chat").blocca is False
    assert letture == ["ats"], "tre chat, una sola connessione"


def test_l_addebito_scala_quello_che_e_appena_uscito(monkeypatch):
    _finge_lettura(monkeypatch, {"mensile": 1_000})
    freno.controlla(TENANT, "chat")
    freno.consumato(TENANT, [("mensile", 400)])
    assert freno.controlla(TENANT, "chat").residuo == 600


def test_quando_gli_addebiti_lo_svuotano_si_rilegge(monkeypatch):
    """La cache non può sapere quello che ENTRA (un pacchetto comprato
    altrove): appena scende a zero la riga sparisce e si torna al database."""
    letture = []
    _finge_lettura(monkeypatch, {"mensile": 100}, letture)
    freno.controlla(TENANT, "chat")
    freno.consumato(TENANT, [("mensile", 100)])
    freno.controlla(TENANT, "chat")
    assert len(letture) == 2


def test_un_rifiuto_non_si_tiene_MAI_in_mente(monkeypatch):
    """Il momento peggiore possibile per essere lenti: chi ha appena comprato
    un pacchetto resterebbe al muro fino alla scadenza della cache."""
    letture = []
    _finge_lettura(monkeypatch, VUOTO, letture)
    monkeypatch.setattr(freno, "_leggi", lambda c, t: (dict(VUOTO), False))
    assert freno.controlla(TENANT, "chat").blocca is True
    assert freno.controlla(TENANT, "chat").blocca is True
    assert freno._memoria == {}, "un fermo in cache è un cliente pagante al muro"


def test_il_saldo_ricordato_scade(monkeypatch):
    letture = []
    _finge_lettura(monkeypatch, {"mensile": 900}, letture)
    freno.controlla(TENANT, "chat")
    monkeypatch.setattr(time, "monotonic", lambda: time.perf_counter() + freno._TTL + 1)
    freno.controlla(TENANT, "chat")
    assert len(letture) == 2


def test_la_memoria_ha_un_tetto(monkeypatch):
    monkeypatch.setattr(ledger, "attivo", lambda: True)
    monkeypatch.setattr(freno, "_leggi", lambda c, t: ({"mensile": 10}, False))
    for i in range(freno._TETTO + 5):
        freno.controlla({"branding": {"tenant_code": f"t{i}"}}, "chat")
    assert len(freno._memoria) <= freno._TETTO


# ── controlla: non blocca mai per un guasto nostro ──────────────────────────

def test_senza_registro_acceso_non_si_blocca_niente(monkeypatch):
    monkeypatch.setattr(ledger, "attivo", lambda: False)
    d = freno.controlla(TENANT, "chat")
    assert d.esito == freno.NON_SO and d.motivo == "registro-spento"


def test_una_chiave_senza_codice_tenant_non_si_blocca(monkeypatch):
    """È il difetto del 6/08 visto dall'altro lato: una chiave senza
    `branding.tenant_code` è un dato che manca a NOI, non un credito finito."""
    monkeypatch.setattr(ledger, "attivo", lambda: True)
    d = freno.controlla({"name": "console", "branding": {}}, "chat")
    assert d.esito == freno.NON_SO and d.motivo == "senza-tenant"


def test_il_freno_rotto_lascia_passare(monkeypatch):
    """Un'eccezione qui trasformerebbe un problema di contabilità in una chat
    rotta — esattamente il difetto che il freno esiste per non produrre."""
    monkeypatch.setattr(ledger, "attivo", lambda: True)
    monkeypatch.setattr(ledger, "codice_tenant",
                        lambda t: (_ for _ in ()).throw(RuntimeError("boom")))
    d = freno.controlla(TENANT, "chat")
    assert d.esito == freno.NON_SO and d.blocca is False


def test_il_saldo_illeggibile_si_ricorda_poco(monkeypatch):
    """Se il database non risponde non ci si ripicchia sopra a ogni messaggio:
    una connessione morta con `connect_timeout` davanti a ogni chat sono
    secondi di attesa prima della prima sillaba."""
    letture = []
    _finge_lettura(monkeypatch, None, letture)
    freno.controlla(TENANT, "chat")
    freno.controlla(TENANT, "chat")
    assert len(letture) == 1
    assert freno._memoria["ats"][1] is None


# ── /chat: il muro, davvero ─────────────────────────────────────────────────

@pytest.fixture
def chat_bloccata(monkeypatch):
    monkeypatch.setattr(tenants, "get_tenant_by_key",
                        lambda k: TENANT if k == "K" else None)
    monkeypatch.setattr(main, "rate_ok", lambda k: True)
    monkeypatch.setattr(ledger, "attivo", lambda: True)
    monkeypatch.setattr(freno, "_leggi", lambda c, t: (dict(VUOTO), False))


def test_la_chat_col_credito_finito_risponde_402(chat_bloccata):
    r = client.post("/chat", json={"message": "ciao"}, headers={"X-Tenant-Key": "K"})
    assert r.status_code == 402
    d = r.json()["detail"]
    assert d["motivo"] == "credito-esaurito" and d["frase"]
    assert d["rinnovo_il"].endswith("-01")


def test_col_credito_finito_il_modello_NON_viene_chiamato(chat_bloccata, monkeypatch):
    chiamate = []
    monkeypatch.setattr(rag, "chat_con_uso",
                        lambda s, u: chiamate.append(1) or ("x", None))
    monkeypatch.setattr(rag, "_retrieve",
                        lambda *a, **k: pytest.fail("nemmeno il retrieval"))
    client.post("/chat", json={"message": "ciao"}, headers={"X-Tenant-Key": "K"})
    assert chiamate == []


def test_lo_stream_col_credito_finito_non_parte_nemmeno(chat_bloccata):
    r = client.post("/chat", json={"message": "ciao", "stream": True},
                    headers={"X-Tenant-Key": "K"})
    assert r.status_code == 402, "il muro arriva prima degli header 200 dello stream"


# ── il percorso non-stream adesso si conta ─────────────────────────────────

def test_una_chat_non_stream_lascia_la_sua_riga(monkeypatch):
    scritte = []
    monkeypatch.setattr(tenants, "get_tenant_by_key", lambda k: TENANT)
    monkeypatch.setattr(main, "rate_ok", lambda k: True)
    monkeypatch.setattr(ledger, "addebita",
                        lambda t, op, u, **kw: scritte.append((op, u)) or
                        {"scritto": True, "token": 0, "righe": []})
    monkeypatch.setattr(rag, "_retrieve", lambda *a, **k: [])
    monkeypatch.setattr(rag, "chat_con_uso", lambda s, u: ("ok", uso.Uso(30, 12)))
    monkeypatch.setattr(rag, "no_answer", lambda lang="it": "non lo so")

    r = client.post("/chat", json={"message": "quanto costa la stampa 3D?"},
                    headers={"X-Tenant-Key": "K"})
    assert r.status_code == 200
    assert len(scritte) == 1, "il percorso senza streaming non contava niente"


def test_una_risposta_che_non_passa_dal_modello_costa_zero_MISURATO(monkeypatch):
    """Un saluto non chiama il modello: costa zero per davvero. Scriverlo come
    `ignoto` sporcherebbe l'unico numero con cui decideremo se il consumo non
    misurato è un problema — inseguiremmo un numero fatto da noi."""
    scritte = []
    monkeypatch.setattr(tenants, "get_tenant_by_key", lambda k: TENANT)
    monkeypatch.setattr(main, "rate_ok", lambda k: True)
    monkeypatch.setattr(ledger, "addebita",
                        lambda t, op, u, **kw: scritte.append(u) or
                        {"scritto": True, "token": 0, "righe": []})
    monkeypatch.setattr(rag, "chat_con_uso",
                        lambda s, u: pytest.fail("un saluto non passa dal modello"))

    r = client.post("/chat", json={"message": "ciao!"}, headers={"X-Tenant-Key": "K"})
    assert r.status_code == 200
    assert len(scritte) == 1
    assert scritte[0] is not None, "«mai chiamato» non è «non misurato»"
    assert (scritte[0].input, scritte[0].output) == (0, 0)
