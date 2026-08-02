"""V8/A · «Cosa so di te»: la memoria che si vede, si usa e si cancella.

Il test che conta è `test_la_lingua_ricordata_cambia_la_risposta`: è la
riproduzione del difetto più istruttivo di Zoey — fra le sue memorie c'era
«Andrea prefers Italian language for business communication», al 70% di
confidenza, e il riassunto finale della stessa conversazione era in inglese.
Ricordava e non se ne serviva. Se un giorno la memoria smette di cambiare la
risposta, questo file diventa rosso.
"""
import pytest
from fastapi.testclient import TestClient

from app import main, memoria, rag
from app.config import settings

TOK = "tok-di-test-lungo-abbastanza-123456"
AUTH = {"Authorization": f"Bearer {TOK}"}


@pytest.fixture(autouse=True)
def pulisci():
    memoria.reset()
    yield
    memoria.reset()


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(settings, "admin_token", TOK)
    return TestClient(main.app)


# ══════════════════════════════════════════════════════════════════════════
# A1 · Lo store: si ricorda, si conferma, si elenca
# ══════════════════════════════════════════════════════════════════════════
def test_ricordare_due_volte_non_fa_due_righe_ma_una_conferma():
    """`conferme` è l'unico criterio onesto che questa pagina possiede: se
    ridire una cosa creasse un doppione, il conteggio non misurerebbe nulla."""
    a = memoria.ricorda("ats", "Preferisci risposte brevi.", chiave="lunghezza",
                        valore="breve", citazione="rispondi in modo breve")
    b = memoria.ricorda("ats", "Preferisci risposte brevi.", chiave="lunghezza",
                        valore="breve", citazione="stai sul breve per favore")
    assert a["id"] == b["id"] and b["conferme"] == 2
    assert len(memoria.elenco("ats")) == 1


def test_una_preferenza_per_chiave_l_ultima_vince():
    memoria.ricorda("ats", "Preferisci l'italiano.", chiave="lingua", valore="it")
    memoria.ricorda("ats", "You prefer English.", chiave="lingua", valore="en")
    assert memoria.preferenze("ats") == {"lingua": "en"}
    assert len(memoria.elenco("ats")) == 1


def test_i_tenant_non_si_vedono_fra_loro():
    """Il confine fra clienti vale anche per quello che il sistema sa di loro:
    sarebbe una perdita di dati mascherata da funzione simpatica."""
    memoria.ricorda("ats", "Preferisci risposte brevi.", chiave="lunghezza", valore="breve")
    assert memoria.elenco("centioni") == [] and memoria.preferenze("centioni") == {}


def test_un_fatto_con_dati_personali_non_si_ricorda():
    """Si SCARTA, non si redige: la stessa regola delle proposte da
    conversazione. Il motore gira ancora in US West."""
    assert memoria.ricorda("ats", "Il referente è mario.rossi@ats.it") is None
    assert memoria.elenco("ats") == []


def test_una_chiave_senza_un_valore_ammesso_non_passa():
    """Una chiave che non porta un valore applicabile è una percentuale al 70%
    con un altro nome: sembra una preferenza e non cambia niente."""
    assert memoria.ricorda("ats", "Preferisci il viola.", chiave="lingua", valore="viola") is None
    assert memoria.ricorda("ats", "Un fatto senza chiave.")["chiave"] == ""


# ══════════════════════════════════════════════════════════════════════════
# A2 · Dimenticare cancella DAVVERO (art. 17), e lascia solo la lapide
# ══════════════════════════════════════════════════════════════════════════
def test_dimenticare_cancella_il_testo_e_lascia_la_lapide():
    m = memoria.ricorda("ats", "Preferisci risposte brevi.", chiave="lunghezza",
                        valore="breve", citazione="stai breve")
    assert memoria.dimentica(m["id"], "andrea") is True
    assert memoria.elenco("ats") == []                    # sparita dalla pagina
    lapidi = memoria.elenco("ats", includi_dimenticate=True)
    assert len(lapidi) == 1
    l = lapidi[0]
    assert l["fatto"] == "" and l["citazione"] == "" and l["valore"] == ""
    assert l["dimenticato_at"] and l["dimenticato_da"] == "andrea"
    assert memoria.preferenze("ats") == {}                # e non agisce più


def test_dimenticare_due_volte_non_e_un_errore_silenzioso():
    m = memoria.ricorda("ats", "Preferisci risposte brevi.")
    assert memoria.dimentica(m["id"]) is True
    assert memoria.dimentica(m["id"]) is False            # lo DICE, non finge
    assert memoria.dimentica("mai-esistita") is False


# ══════════════════════════════════════════════════════════════════════════
# A3 · Nessuna percentuale finta: la fonte al posto del numero
# ══════════════════════════════════════════════════════════════════════════
def test_nessuna_confidenza_nel_record():
    """In Zoey tutte le memorie sono al 70%. Qui non c'è nessun campo che possa
    diventarlo per distrazione: ci sono un conteggio e una frase."""
    m = memoria.ricorda("ats", "Preferisci risposte brevi.", citazione="stai breve")
    assert "confidenza" not in m and "confidence" not in m
    assert m["conferme"] == 1 and m["citazione"] == "stai breve"


def test_la_citazione_e_la_frase_vera_non_tutto_il_messaggio():
    v = memoria.dalla_frase("Ciao, tutto bene? Rispondimi in inglese d'ora in poi. Grazie.")
    assert v and v["chiave"] == "lingua" and v["valore"] == "en"
    assert v["citazione"] == "Rispondimi in inglese d'ora in poi"


# ══════════════════════════════════════════════════════════════════════════
# Il riconoscitore: prudente, senza modello
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("frase,chiave,valore", [
    ("parlami in italiano", "lingua", "it"),
    ("d'ora in poi rispondimi in inglese", "lingua", "en"),
    ("please answer in English", "lingua", "en"),
    ("rispondi in modo breve", "lunghezza", "breve"),
    ("keep it short", "lunghezza", "breve"),
    ("rispondi più in dettaglio", "lunghezza", "estesa"),
])
def test_riconosce_le_preferenze_dichiarate(frase, chiave, valore):
    v = memoria.dalla_frase(frase)
    assert v and (v["chiave"], v["valore"]) == (chiave, valore)


@pytest.mark.parametrize("frase", [
    "com'è il tempo in italiano?",           # «italiano» c'è, la richiesta no
    "traduci questo documento in inglese",   # è un compito, non una preferenza
    "ciao",
    "",
])
def test_non_inventa_preferenze_dove_non_ci_sono(frase):
    assert memoria.dalla_frase(frase) is None


def test_una_preferenza_con_dentro_una_email_non_passa():
    assert memoria.dalla_frase("scrivi a mario@ats.it e rispondimi in inglese") is None


# ══════════════════════════════════════════════════════════════════════════
# A4 · LA MEMORIA SI USA — il difetto di Zoey, riprodotto e bloccato
# ══════════════════════════════════════════════════════════════════════════
def test_il_prompt_porta_i_ricordi_e_dice_che_non_sono_fonti():
    p = rag._system("it", memoria=["Preferisci risposte brevi."])
    assert "COSA SAI DI CHI TI PARLA" in p and "Preferisci risposte brevi." in p
    assert "non citarle mai come" in p            # non sono CONTENUTO
    assert rag._system("it", memoria=[]) == rag._system("it")   # senza ricordi, prompt identico


def _tenant_finto(monkeypatch, code="ats"):
    """Un tenant vero quanto basta: la chiave, lo scope, nessun default di lingua."""
    t = {"name": code, "tenant_code": code, "allowed_scopes": [code],
         "branding": {}, "allowed_origins": [], "quota_day": None}
    monkeypatch.setattr(main.tenants, "get_tenant_by_key", lambda k: dict(t) if k == "k-ats" else None)
    monkeypatch.setattr(main.tenants, "quota_ok", lambda t2: True)
    return t


def test_la_lingua_ricordata_cambia_la_risposta(client, monkeypatch):
    """IL test del blocco.

    Zoey teneva «prefers Italian» e rispondeva in inglese. Qui si registra la
    preferenza opposta (inglese) su un tenant il cui default è l'italiano, si fa
    una domanda SENZA indicare la lingua, e si guarda quale prompt di sistema è
    finito davanti al modello. Se la memoria smette di essere letta, `lang`
    torna a 'it' e questo test diventa rosso."""
    _tenant_finto(monkeypatch)
    monkeypatch.setattr(settings, "default_lang", "it")
    visti = {}

    def finto_answer(question, grants, **kw):
        visti.update(kw)
        return {"answer": "ok", "sources": [], "scopes": ["ats"]}

    monkeypatch.setattr(main.rag, "answer", finto_answer)
    memoria.ricorda("ats", "You prefer answers in English.", chiave="lingua", valore="en")

    r = client.post("/chat", json={"message": "quanto costa la stampa 3D?"},
                    headers={"X-Tenant-Key": "k-ats"})
    assert r.status_code == 200
    assert visti["lang"] == "en"          # ← il cuore: la memoria ha cambiato la risposta
    assert "You prefer answers in English." in visti["memoria"]


def test_una_lingua_chiesta_adesso_batte_quella_ricordata(client, monkeypatch):
    """Un'istruzione di adesso vale più di una di ieri, sempre: altrimenti la
    memoria diventa una gabbia invece di una comodità."""
    _tenant_finto(monkeypatch)
    visti = {}
    monkeypatch.setattr(main.rag, "answer",
                        lambda q, g, **kw: (visti.update(kw), {"answer": "ok", "sources": [], "scopes": []})[1])
    memoria.ricorda("ats", "You prefer answers in English.", chiave="lingua", valore="en")
    client.post("/chat", json={"message": "ciao come va", "lang": "it"},
                headers={"X-Tenant-Key": "k-ats"})
    assert visti["lang"] == "it"


def test_dirlo_in_chat_lo_registra_e_vale_gia_da_subito(client, monkeypatch):
    """Non «dalla prossima volta»: la frase che dichiara la preferenza cambia
    già la risposta in cui è stata detta — è lì che si vede che ha funzionato."""
    _tenant_finto(monkeypatch)
    monkeypatch.setattr(settings, "default_lang", "it")
    visti = {}
    monkeypatch.setattr(main.rag, "answer",
                        lambda q, g, **kw: (visti.update(kw), {"answer": "ok", "sources": [], "scopes": []})[1])
    r = client.post("/chat", json={"message": "d'ora in poi rispondimi in inglese"},
                    headers={"X-Tenant-Key": "k-ats"})
    assert visti["lang"] == "en"
    # e lo DICE nella risposta, con l'id per dimenticarlo subito
    ric = r.json().get("ricordato")
    assert ric and ric["id"] and "English" in ric["fatto"]
    assert memoria.preferenze("ats") == {"lingua": "en"}


def test_dimenticata_la_preferenza_la_risposta_torna_come_prima(client, monkeypatch):
    """Il bottone DIMENTICA deve avere un effetto VERO sul comportamento, non
    solo togliere una riga da una pagina."""
    _tenant_finto(monkeypatch)
    monkeypatch.setattr(settings, "default_lang", "it")
    visti = {}
    monkeypatch.setattr(main.rag, "answer",
                        lambda q, g, **kw: (visti.update(kw), {"answer": "ok", "sources": [], "scopes": []})[1])
    m = memoria.ricorda("ats", "You prefer answers in English.", chiave="lingua", valore="en")
    memoria.dimentica(m["id"], "andrea")
    client.post("/chat", json={"message": "quanto costa?"}, headers={"X-Tenant-Key": "k-ats"})
    assert visti["lang"] == "it"
    assert visti["memoria"] == []


def test_la_memoria_non_allarga_i_permessi(client, monkeypatch):
    """Come per il filo (V7/A1): quello che il sistema ricorda di te non è un
    permesso. I grant si ricalcolano dalla chiave, sempre."""
    _tenant_finto(monkeypatch)
    visti = {}
    monkeypatch.setattr(main.rag, "answer",
                        lambda q, g, **kw: (visti.update({"grants": g, **kw}),
                                            {"answer": "ok", "sources": [], "scopes": []})[1])
    memoria.ricorda("ats", "Preferisci risposte brevi.", chiave="lunghezza", valore="breve")
    client.post("/chat", json={"message": "ciao"}, headers={"X-Tenant-Key": "k-ats"})
    grants = visti["grants"]
    piatti = grants if isinstance(grants, list) else sum((list(v) for v in grants.values()), [])
    assert "*" not in piatti and set(piatti) <= {"ats"}


# ══════════════════════════════════════════════════════════════════════════
# La pagina, via API
# ══════════════════════════════════════════════════════════════════════════
def test_la_pagina_elenca_e_dichiara_se_e_persistente(client):
    memoria.ricorda("ats", "Preferisci risposte brevi.", chiave="lunghezza",
                    valore="breve", citazione="stai breve")
    d = client.get("/admin/memoria?tenant=ats", headers=AUTH).json()
    assert d["totale"] == 1 and d["usate"] == {"lunghezza": "breve"}
    assert d["persist"] is False           # in test non c'è DB, e lo dice
    riga = d["memorie"][0]
    assert riga["citazione"] == "stai breve" and riga["conferme"] == 1
    assert "confidenza" not in riga


def test_il_bottone_dimentica_passa_dall_api(client):
    m = memoria.ricorda("ats", "Preferisci risposte brevi.")
    r = client.post("/admin/memoria/dimentica", headers=AUTH,
                    json={"id": m["id"], "by": "andrea"})
    assert r.status_code == 200
    assert client.get("/admin/memoria?tenant=ats", headers=AUTH).json()["totale"] == 0
    assert client.post("/admin/memoria/dimentica", headers=AUTH,
                       json={"id": m["id"]}).status_code == 404


def test_la_memoria_e_roba_da_admin(client):
    assert client.get("/admin/memoria?tenant=ats").status_code == 401
    assert client.post("/admin/memoria", json={"tenant": "ats", "fatto": "x"}).status_code == 401
    assert client.post("/admin/memoria/dimentica", json={"id": "x"}).status_code == 401


def test_aggiungere_a_mano_un_fatto(client):
    r = client.post("/admin/memoria", headers=AUTH,
                    json={"tenant": "ats", "fatto": "Fatturano a fine mese."})
    assert r.status_code == 200 and r.json()["memoria"]["origine"] == "mano"
    assert client.post("/admin/memoria", headers=AUTH,
                       json={"tenant": "ats", "fatto": "scrivi a mario@ats.it"}).status_code == 422
