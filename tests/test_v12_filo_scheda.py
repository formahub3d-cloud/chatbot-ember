"""V12/B · La domanda di seguito deve trovare la SCHEDA, non solo la KB.

Il difetto, provato due volte in produzione il 3/08. Due turni, come li farebbe
una persona:

    «Parlami del cliente HRH»       → giusto, trova le note di HRH
    «E quanto paga al mese?»        → «Questo nel cervello non c'è.»

Mentre nel vault c'è scritto: **HRH, 200 €/mese**. Le fonti restituite erano
`kb-hrh` — la scheda pubblica, quella che il bot mostra ai visitatori — invece
di `cliente-hrh`, dove sta la cifra.

**Il sospetto era che l'espansione aggiungesse parole che somigliano alla KB.
Misurato: l'espansione non partiva affatto.** `_ANAFORA` accettava «e» solo se
seguita da un articolo o una preposizione («e il contratto?»), quindi ogni
domanda di seguito che comincia con una parola interrogativa cadeva fuori e
finiva nel retrieval **senza soggetto**. Cercare «quanto paga al mese» in tutto
lo scope trova la nota che parla di pagamenti — non quella che parla di HRH.

La correzione non è nel filo: è in COSA il filo riconosce.
"""
import pytest

from app import filo, rag

FILO_HRH = [
    {"role": "user", "content": "Parlami del cliente HRH"},
    {"role": "assistant", "content": "HRH è un cliente di FORMA: sito e assistenza."},
]

# Le due note che si contendono la domanda. Sono quelle vere, accorciate.
NOTE = [
    {"slug": "kb-hrh", "title": "HRH — knowledge base pubblica",
     "text": "Orari, servizi e modalità di pagamento per chi scrive a HRH. "
             "Si paga al momento del servizio, mensilmente o a consumo."},
    {"slug": "cliente-hrh", "title": "Cliente — HRH",
     "text": "Scheda cliente HRH. Stato: attivo. Contratto: 200 €/mese di "
             "assistenza e manutenzione del sito."},
]


def _indice_finto(monkeypatch):
    """Un retrieval che sceglie per SOVRAPPOSIZIONE DI PAROLE con la query.

    Grezzo di proposito, e sufficiente: qui non si misura la qualità degli
    embedding, si misura che **la query cambia la nota che vince** — che è
    esattamente il difetto. Con un indice finto il test resta offline e resta
    vero anche se domani si cambia provider."""
    visti = {}

    def parole(t):
        import re
        return {w for w in re.findall(r"[\wÀ-ÿ']+", (t or "").lower()) if len(w) > 2}

    def finto(q, grants, k=6, **kw):
        visti["q"] = q
        pq = parole(q)
        segnate = sorted(NOTE, key=lambda n: -len(pq & parole(n["title"] + " " + n["text"])))
        migliore = segnate[0]
        if not (pq & parole(migliore["title"] + " " + migliore["text"])):
            return []

        class H:
            score = 0.9
            payload = {"text": migliore["text"], "slug": migliore["slug"],
                       "title": migliore["title"], "tenant": "hrh",
                       "path": f"forma/clienti/hrh/{migliore['slug']}.md"}
        return [H()]

    monkeypatch.setattr(rag, "_retrieve", finto)
    return visti


# ══════════════════════════════════════════════════════════════════════════
# La prova che resta: due turni, e la cifra nella risposta
# ══════════════════════════════════════════════════════════════════════════
def test_la_domanda_di_seguito_trova_la_scheda_col_prezzo(monkeypatch):
    """IL caso del 3/08. Se torna rosso, Divina ha ricominciato a dire che non
    lo sa mentre nel vault la cifra c'è."""
    visti = _indice_finto(monkeypatch)
    monkeypatch.setattr(rag, "chat",
                        lambda s, u: "HRH paga 200 €/mese." if "200" in u
                        else "Non lo trovo.")
    r = rag.answer("E quanto paga al mese?", ["hrh"], history=FILO_HRH)
    assert "HRH" in visti["q"], "la query è partita senza il soggetto"
    assert [f["slug"] for f in r["sources"]] == ["cliente-hrh"], \
        "ha pescato la KB pubblica invece della scheda"
    assert "200" in r["answer"]
    assert r["answer"] != rag.NO_ANSWER


def test_senza_l_espansione_pescherebbe_la_kb(monkeypatch):
    """Il controfattuale, per essere sicuri che sia la QUERY a fare la
    differenza e non un caso fortunato dell'indice finto."""
    visti = _indice_finto(monkeypatch)
    monkeypatch.setattr(rag, "chat", lambda s, u: "x")
    r = rag.answer("E quanto paga al mese?", ["hrh"], history=[])   # niente filo
    assert visti["q"] == "E quanto paga al mese?"
    assert [f["slug"] for f in r["sources"]] == ["kb-hrh"]


# ══════════════════════════════════════════════════════════════════════════
# Il riconoscitore: cosa è di seguito e cosa si regge da solo
# ══════════════════════════════════════════════════════════════════════════
def test_le_domande_di_seguito_che_prima_cadevano_fuori():
    """Tutte cominciano con una parola interrogativa e non nominano nessuno:
    è la forma più comune di domanda di seguito, ed era quella scoperta."""
    for d in ("E quanto paga al mese?", "Quanto paga al mese?", "Che scope ha?",
              "Da quando è cliente?", "Quanto fattura?"):
        assert filo.e_di_seguito(d, FILO_HRH), d
        assert "HRH" in filo.query_retrieval(d, FILO_HRH), d


def test_una_domanda_col_proprio_soggetto_resta_sola():
    """«la stampa 3D» è un soggetto anche senza maiuscola: un articolo nudo lo
    introduce. Espanderla ci attaccherebbe il cliente del turno prima."""
    for d in ("quanto costa la stampa 3D?", "quali sono gli orari del laboratorio?",
              "Parlami di ATS"):
        assert not filo._ellittica(d), d


def test_al_mese_non_e_un_soggetto():
    """La distinzione che regge la regola: un articolo NUDO introduce un
    soggetto, una preposizione articolata («al mese», «del sito») no."""
    assert filo._ellittica("E quanto paga al mese?")
    assert not filo._ellittica("E quanto costa il mese?")


def test_un_saluto_non_si_espande():
    """Senza il punto interrogativo non è una domanda: «ciao» dopo una
    conversazione su HRH non deve diventare una ricerca su HRH."""
    assert not filo.e_di_seguito("ciao", FILO_HRH)
    assert filo.query_retrieval("ciao", FILO_HRH) == "ciao"


def test_il_filo_non_allarga_i_permessi_nemmeno_adesso(monkeypatch):
    """La regola del V7, ricontrollata su una porta nuova: espandere di più
    significa cercare di più, mai vedere di più."""
    visti = {}
    monkeypatch.setattr(rag, "_retrieve",
                        lambda q, grants, *a, **k: (visti.update(g=grants), [])[1])
    monkeypatch.setattr(rag, "chat", lambda s, u: "x")
    rag.answer("Quanto paga al mese?", ["ats"],
               history=[{"role": "user", "content": "Parlami di andrea-aloia e HRH"}])
    assert visti["g"] == ["ats"]
