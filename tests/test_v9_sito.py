"""V9/B · La KB di un cliente nasce dal suo sito, come proposta.

Il blocco che vale di più del giro, e quello dove sbagliare costa di più: una
scheda cliente inventata è peggio di una vuota, perché sembra verificata. Le tre
regole non negoziabili sono provate qui una per una — la fonte, i dati personali,
la scrittura che non parte da sola.
"""
import pytest
from fastapi.testclient import TestClient

from app import main, proposals, sitokb, websearch
from app.config import settings

TOK = "tok-di-test-lungo-abbastanza-123456"
AUTH = {"Authorization": f"Bearer {TOK}"}

HOME = ("ATS è un'azienda di ristorazione di Benevento. "
        "Dal 2018 portiamo la nostra cucina a casa vostra, in tutta la provincia. "
        "Lavoriamo con prodotti del territorio e cuciniamo ogni giorno in sede, "
        "senza semilavorati: è la ragione per cui abbiamo aperto e non è cambiata. "
        "Serviamo privati, uffici e piccoli eventi in tutta la provincia di Benevento.")
SERVIZI = ("I nostri servizi: catering per eventi, pranzi in ufficio e consegna a "
           "domicilio. Gli ordini ricevuti entro le 11 vengono consegnati in giornata. "
           "Per il catering serve un preavviso di almeno tre giorni lavorativi, e il "
           "menù si concorda insieme. I pranzi in ufficio hanno una formula fissa "
           "settimanale, con due primi e due secondi che cambiano ogni giorno.")
CONTATTI = ("Scrivici a info@ats.it oppure passa in via Roma 12, Benevento. "
            "Il responsabile commerciale è Mario Rossi — direttore vendite. "
            "Siamo aperti dal lunedì al venerdì, dalle 9 alle 18, e il sabato mattina "
            "su appuntamento. La cucina chiude alle 22 tutti i giorni tranne la domenica.")

PAGINE = [
    {"url": "https://ats.it", "titolo": "ATS", "testo": HOME},
    {"url": "https://ats.it/servizi", "titolo": "Servizi", "testo": SERVIZI},
    {"url": "https://ats.it/contatti", "titolo": "Contatti", "testo": CONTATTI},
]


@pytest.fixture(autouse=True)
def _pulizia():
    proposals.reset()
    yield
    proposals.reset()


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(settings, "admin_token", TOK)
    return TestClient(main.app)


# ══════════════════════════════════════════════════════════════════════════
# L'indirizzo
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("dentro,fuori", [
    ("ats.it", "https://ats.it"),
    ("https://ats.it/", "https://ats.it"),
    ("http://www.ats.it/chi-siamo", "http://www.ats.it/chi-siamo"),
    ("non un indirizzo", ""),
    ("", ""),
    ("ftp://ats.it", ""),
])
def test_l_indirizzo_si_normalizza_o_si_rifiuta(dentro, fuori):
    assert sitokb.normalizza_url(dentro) == fuori


# ══════════════════════════════════════════════════════════════════════════
# Regola 1 · Ogni pezzo porta la sua fonte, e la fonte si VERIFICA
# ══════════════════════════════════════════════════════════════════════════
def test_una_citazione_che_non_si_ritrova_fa_cadere_la_voce():
    """È la regola che separa una scheda da una voce di corridoio. Il modello
    che «cita» ricostruendo a memoria è il modo esatto in cui una cosa
    plausibile diventa un dato del cervello."""
    voci = sitokb.filtra([
        {"sezione": "servizi", "titolo": "Consegna in giornata", "url": "https://ats.it/servizi",
         "contenuto": "Consegne in giornata.",
         "citazione": "gli ordini ricevuti entro le 11 vengono consegnati in giornata"},
        {"sezione": "servizi", "titolo": "Consegna in 30 minuti", "url": "https://ats.it/servizi",
         "contenuto": "Consegne rapidissime.",
         "citazione": "consegniamo in trenta minuti in tutta Italia"},   # mai scritto
    ], PAGINE, "ats")
    assert [v["titolo"] for v in voci] == ["Consegna in giornata"]


def test_la_voce_porta_l_url_della_pagina_giusta():
    v = sitokb.filtra([
        {"sezione": "identita", "titolo": "Chi sono", "url": "https://ats.it",
         "contenuto": "Ristorazione a Benevento.",
         "citazione": "Dal 2018 portiamo la nostra cucina a casa vostra"},
    ], PAGINE, "ats")
    assert v and v[0]["url"] == "https://ats.it"


def test_url_sbagliato_ma_frase_vera_tiene_la_frase_e_corregge_l_indirizzo():
    """Un modello che sbaglia pagina ma cita bene ha detto una cosa vera con
    l'indirizzo sbagliato: si tiene la frase e si corregge l'indirizzo, invece
    di buttare via un dato buono o di pubblicare una fonte che non lo contiene."""
    v = sitokb.filtra([
        {"sezione": "servizi", "titolo": "Consegna", "url": "https://ats.it",   # sbagliato
         "contenuto": "Consegne in giornata.",
         "citazione": "gli ordini ricevuti entro le 11 vengono consegnati in giornata"},
    ], PAGINE, "ats")
    assert v and v[0]["url"] == "https://ats.it/servizi"


def test_senza_scope_non_esce_niente():
    """Una voce senza cartella cliente non ha un posto dove andare: sarebbe una
    nota che atterra dove capita."""
    assert sitokb.filtra([{"sezione": "identita", "titolo": "x", "contenuto": "y",
                           "citazione": "Dal 2018 portiamo la nostra cucina",
                           "url": "https://ats.it"}], PAGINE, "") == []


def test_una_sezione_inventata_si_scarta():
    assert sitokb.filtra([{"sezione": "meteo", "titolo": "x", "contenuto": "y",
                           "citazione": "Dal 2018 portiamo la nostra cucina",
                           "url": "https://ats.it"}], PAGINE, "ats") == []


# ══════════════════════════════════════════════════════════════════════════
# Regola 2 · Niente persone. Ma i recapiti dell'AZIENDA sì, ed è dichiarato
# ══════════════════════════════════════════════════════════════════════════
def test_una_persona_fisica_non_entra_nella_scheda():
    """Il caso che capita su ogni pagina «chi siamo»: nome, cognome e ruolo."""
    v = sitokb.filtra([
        {"sezione": "identita", "titolo": "Il commerciale", "url": "https://ats.it/contatti",
         "contenuto": "Il responsabile commerciale è Mario Rossi — direttore vendite.",
         "citazione": "Il responsabile commerciale è Mario Rossi — direttore vendite"},
    ], PAGINE, "ats")
    assert v == []


def test_il_recapito_aziendale_entra_perche_e_il_motivo_della_sezione():
    """La deroga, dichiarata: un bot che non sa dire dove sei non serve a niente.
    Vale SOLO nella sezione contatti e SOLO per recapiti d'azienda."""
    v = sitokb.filtra([
        {"sezione": "contatti", "titolo": "Come contattarci", "url": "https://ats.it/contatti",
         "contenuto": "Si scrive a info@ats.it, oppure si passa in via Roma 12 a Benevento.",
         "citazione": "Scrivici a info@ats.it oppure passa in via Roma 12"},
    ], PAGINE, "ats")
    assert len(v) == 1 and "info@ats.it" in v[0]["contenuto"]


def test_una_email_personale_cade_anche_nei_contatti():
    v = sitokb.filtra([
        {"sezione": "contatti", "titolo": "Commerciale", "url": "https://ats.it/contatti",
         "contenuto": "Scrivere a mario.rossi@ats.it.",
         "citazione": "Scrivici a info@ats.it oppure passa in via Roma 12"},
    ], PAGINE, "ats")
    assert v == []


def test_fuori_dai_contatti_vale_la_regola_secca():
    """Nelle altre sezioni resta la regola di learned.py: si scarta, non si redige."""
    v = sitokb.filtra([
        {"sezione": "servizi", "titolo": "Ordini", "url": "https://ats.it/servizi",
         "contenuto": "Per ordinare scrivi a info@ats.it.",
         "citazione": "gli ordini ricevuti entro le 11 vengono consegnati in giornata"},
    ], PAGINE, "ats")
    assert v == []


# ══════════════════════════════════════════════════════════════════════════
# Regola 3 · Nessuna scrittura automatica
# ══════════════════════════════════════════════════════════════════════════
def test_proporre_non_scrive_niente_nel_vault(monkeypatch):
    scritture = []
    monkeypatch.setattr(main.writeback, "save_note",
                        lambda *a, **k: scritture.append(a) or {"created": True})
    monkeypatch.setattr(settings, "tavily_api_key", "t")
    monkeypatch.setattr(sitokb, "leggi", lambda u: list(PAGINE))
    monkeypatch.setattr(sitokb, "chat", lambda sys, usr: (
        '{"voci":[{"sezione":"identita","titolo":"Chi sono","contenuto":"Ristorazione.",'
        '"citazione":"Dal 2018 portiamo la nostra cucina a casa vostra",'
        '"url":"https://ats.it"}]}'))
    r = sitokb.proponi("ats", "ats.it")
    assert len(r["voci"]) == 1
    assert scritture == []                      # ← il punto


def test_le_voci_finiscono_in_coda_e_portano_la_fonte_fin_li():
    proposals.add_sito([{"sezione": "servizi", "titolo": "Consegna in giornata",
                         "contenuto": "Entro le 11.", "scope": "ats",
                         "citazione": "gli ordini ricevuti entro le 11",
                         "url": "https://ats.it/servizi"}], url="https://ats.it")
    p = [x for x in proposals.generate() if x["source"] == "sito"]
    assert len(p) == 1
    assert p[0]["url"] == "https://ats.it/servizi" and p[0]["citazione"]
    assert p[0]["scope"] == "ats" and "ats" in p[0]["title"]


def test_approvare_scrive_UNA_nota_marcata_con_la_pagina_dentro(monkeypatch):
    """La marcatura «NON verificato» pesa più qui che altrove: quel testo il
    cliente l'ha scritto per i suoi visitatori, non per noi."""
    salvate = []

    def finto(scope, titolo, corpo, summary="", tags=None, overwrite=False):
        salvate.append({"scope": scope, "titolo": titolo, "corpo": corpo,
                        "summary": summary, "tags": tags})
        return {"path": f"forma/clienti/{scope}/x.md", "slug": "x", "created": True}

    monkeypatch.setattr("app.writeback.save_note", finto)
    proposals.add_sito([{"sezione": "servizi", "titolo": "Consegna in giornata",
                         "contenuto": "Entro le 11.", "scope": "ats",
                         "citazione": "gli ordini ricevuti entro le 11",
                         "url": "https://ats.it/servizi"}])
    pid = [x for x in proposals.generate() if x["source"] == "sito"][0]["id"]
    res = proposals.approve(pid)
    assert res and res["kind"] == "sito" and len(salvate) == 1
    n = salvate[0]
    assert n["scope"] == "ats" and n["titolo"] == "Consegna in giornata"
    assert "NON verificato" in n["corpo"] and "https://ats.it/servizi" in n["corpo"]
    assert "gli ordini ricevuti entro le 11" in n["corpo"]
    assert "sito-cliente" in n["tags"] and "da-verificare" in n["tags"]
    # e sparisce dalla coda: approvata una volta, non due
    assert not [x for x in proposals.generate() if x["id"] == pid]


def test_rilanciare_sullo_stesso_sito_non_duplica_la_coda():
    v = [{"sezione": "servizi", "titolo": "Consegna", "contenuto": "x", "scope": "ats",
          "citazione": "y", "url": "https://ats.it/servizi"}]
    assert len(proposals.add_sito(v)) == 1
    assert len(proposals.add_sito(v)) == 0
    assert len([x for x in proposals.generate() if x["source"] == "sito"]) == 1


# ══════════════════════════════════════════════════════════════════════════
# Inerzia dichiarata: senza chiave non finge, e non tace
# ══════════════════════════════════════════════════════════════════════════
def test_senza_chiave_tavily_lo_dice_invece_di_tornare_vuoto(monkeypatch):
    """Una lista vuota muta farebbe concludere che il cliente non ha un sito."""
    monkeypatch.setattr(settings, "tavily_api_key", "")
    r = sitokb.proponi("ats", "ats.it")
    assert r["voci"] == [] and "TAVILY_API_KEY" in r["perche"]
    assert websearch.estrai(["https://ats.it"]) == {}


def test_un_sito_illeggibile_lo_dice(monkeypatch):
    monkeypatch.setattr(settings, "tavily_api_key", "t")
    monkeypatch.setattr(sitokb, "leggi", lambda u: [])
    assert "nessuna pagina" in sitokb.proponi("ats", "ats.it")["perche"]


def test_un_sito_quasi_vuoto_lo_dice_col_numero(monkeypatch):
    monkeypatch.setattr(settings, "tavily_api_key", "t")
    monkeypatch.setattr(sitokb, "leggi",
                        lambda u: [{"url": "https://ats.it", "titolo": "x", "testo": "poco testo qui"}])
    r = sitokb.proponi("ats", "ats.it")
    assert r["voci"] == [] and "pochissimo testo" in r["perche"]


def test_zero_voci_dopo_i_controlli_si_spiega(monkeypatch):
    """«Zero» dopo aver letto tutto è un esito diverso da «zero perché non ho
    letto niente», e la differenza va detta a chi guarda."""
    monkeypatch.setattr(settings, "tavily_api_key", "t")
    monkeypatch.setattr(sitokb, "leggi", lambda u: list(PAGINE))
    monkeypatch.setattr(sitokb, "chat", lambda s, u: '{"voci":[]}')
    r = sitokb.proponi("ats", "ats.it")
    assert r["voci"] == [] and "superato i controlli" in r["perche"]
    assert r["pagine"] == [p["url"] for p in PAGINE]


# ══════════════════════════════════════════════════════════════════════════
# L'endpoint
# ══════════════════════════════════════════════════════════════════════════
def test_l_endpoint_accoda_e_dichiara_il_degrado(client, monkeypatch):
    monkeypatch.setattr(settings, "tavily_api_key", "t")
    monkeypatch.setattr(main.sitokb, "leggi", lambda u: list(PAGINE))
    monkeypatch.setattr(main.sitokb, "chat", lambda s, u: (
        '{"voci":[{"sezione":"identita","titolo":"Chi sono","contenuto":"Ristorazione.",'
        '"citazione":"Dal 2018 portiamo la nostra cucina a casa vostra","url":"https://ats.it"}]}'))
    r = client.post("/admin/clients/kb-da-sito", headers=AUTH,
                    json={"scope": "ats", "url": "ats.it"})
    assert r.status_code == 200
    d = r.json()
    assert d["accodate"] == 1 and d["url"] == "https://ats.it"
    assert d["degrado"]["stato"] == "acceso"


def test_l_endpoint_e_solo_admin_e_vuole_uno_scope(client):
    assert client.post("/admin/clients/kb-da-sito",
                       json={"scope": "ats", "url": "ats.it"}).status_code == 401
    assert client.post("/admin/clients/kb-da-sito", headers=AUTH,
                       json={"scope": "", "url": "ats.it"}).status_code == 422
