"""V10/C · Le cinque prove della conversazione vera.

Il criterio, al posto dell'elenco delle funzioni: **una conversazione funziona
quando chi parla non deve pensare a come parlare.** In quattro giri sono state
aggiunte sei cose fatte bene e l'area è passata da 4 a 6, ma sei funzioni non
fanno una conversazione: Divina rispondeva bene se le facevi la domanda giusta
nel modo giusto.

Queste cinque prove sono il metro dell'area, ed è per questo che stanno in un
file loro con `PROVE` in fondo: da adesso il punteggio della conversazione si
GIUSTIFICA con quante ne passano, invece di salire di un punto ogni volta che si
aggiunge una funzione.

Nessuna chiama il modello. Tutte e cinque misurano una cosa sola e concreta:
**cosa si va a cercare** — perché è lì che una mossa di conversazione diventa una
risposta diversa, e perché è l'unica parte verificabile senza un LLM in mezzo.
"""
import pytest

from app import conversa, filo, rag

# Il filo di partenza: si è parlato di due clienti, come nella prova numero due.
FILO_DUE = [
    {"role": "user", "content": "Parlami del cliente ATS"},
    {"role": "assistant", "content": "ATS è il pilota: impianti, scheda in forma/clienti/ats."},
    {"role": "user", "content": "E la scheda di Centioni?"},
    {"role": "assistant", "content": "Centioni ha una scheda più corta, 61 righe."},
]
FILO_UNO = [
    {"role": "user", "content": "Quanto costa il listino 2026?"},
    {"role": "assistant", "content": "Il listino 2026 parte da 300 euro al mese."},
]


# ══════════════════════════════════════════════════════════════════════════
# PROVA 1 · «Aspetta, non intendevo quello» → torna indietro di UN turno
# ══════════════════════════════════════════════════════════════════════════
def test_prova1_la_correzione_non_ricerca_la_frase_ritirata():
    """Il difetto che questa prova toglie: il filo, da solo, riconosce
    l'anafora e ANTEPONE gli ultimi due turni utente — cioè rimette nella query
    proprio la frase che la persona ha appena ritirato. Più contesto e più
    sbagliato, ed è il modo più sicuro di sembrare sordi."""
    d = "Aspetta, non intendevo quello"
    assert conversa.mossa(d, FILO_DUE) == "correzione"
    q = conversa.query(d, FILO_DUE)
    assert "Centioni" not in q                    # il turno ritirato esce
    assert "ATS" in q                             # quello prima resta: è il «indietro di uno»
    # e senza la mossa il filo ci avrebbe rimesso dentro proprio quello
    assert "Centioni" in filo.query_retrieval(d, FILO_DUE)


def test_prova1_la_correzione_che_porta_il_soggetto_giusto():
    d = "No, intendevo il listino"
    assert conversa.mossa(d, FILO_DUE) == "correzione"
    assert "listino" in conversa.query(d, FILO_DUE)


def test_prova1_dice_al_modello_di_non_ricominciare():
    i = conversa.istruzione("correzione")
    assert "UN turno" in i and "non ricominciare" in i


# ══════════════════════════════════════════════════════════════════════════
# PROVA 2 · «E l'altro?» dopo due clienti → chiede QUALE, non indovina
# ══════════════════════════════════════════════════════════════════════════
def test_prova2_con_due_soggetti_chiede_quale():
    assert conversa.mossa("E l'altro?", FILO_DUE) == "ambiguo"
    c = conversa.chiarimento("E l'altro?", FILO_DUE)
    assert c and "ATS" in c["answer"] and "Centioni" in c["answer"]
    assert "?" in c["answer"]


def test_prova2_con_un_soggetto_solo_non_e_ambiguo():
    """Un chiarimento chiesto quando non serve è fastidioso quanto una risposta
    indovinata: con un soggetto solo si risponde e basta."""
    assert conversa.mossa("E l'altro?", FILO_UNO) != "ambiguo"


def test_prova2_non_indovina_e_non_cerca(monkeypatch):
    """La prova vera: dal percorso completo non esce una risposta su UNO dei
    due. Il retrieval non viene nemmeno chiamato — non può indovinare, non
    soltanto è improbabile che lo faccia."""
    monkeypatch.setattr(rag, "_retrieve",
                        lambda *a, **k: pytest.fail("non deve cercare: deve chiedere"))
    monkeypatch.setattr(rag, "chat", lambda *a, **k: pytest.fail("non serve il modello"))
    r = rag.answer("E l'altro?", ["forma-core"], history=FILO_DUE)
    assert r["mossa"] == "ambiguo" and r["sources"] == []
    assert set(r["chiarimento"]) == {"ATS", "Centioni"}


# ══════════════════════════════════════════════════════════════════════════
# PROVA 3 · «Lascia stare, dimmi invece…» → abbandona senza rispondere lo stesso
# ══════════════════════════════════════════════════════════════════════════
def test_prova3_abbandonare_taglia_il_filo():
    d = "Lascia stare, dimmi invece quanto costa il listino"
    assert conversa.mossa(d, FILO_DUE) == "abbandono"
    q = conversa.query(d, FILO_DUE)
    assert "listino" in q
    assert "ATS" not in q and "Centioni" not in q       # il vecchio non torna


def test_prova3_abbandonare_senza_niente_dopo_non_risponde_lo_stesso(monkeypatch):
    monkeypatch.setattr(rag, "_retrieve",
                        lambda *a, **k: pytest.fail("l'argomento è stato abbandonato"))
    monkeypatch.setattr(rag, "chat", lambda *a, **k: pytest.fail("non serve il modello"))
    r = rag.answer("Lascia stare", ["forma-core"], history=FILO_DUE)
    assert r["mossa"] == "abbandono" and r["sources"] == []
    assert "lascio stare" in r["answer"].lower()
    assert "ATS" not in r["answer"]


# ══════════════════════════════════════════════════════════════════════════
# PROVA 4 · «Ma sei sicura?» → riapre la fonte, non ripete con altre parole
# ══════════════════════════════════════════════════════════════════════════
def test_prova4_il_dubbio_ricerca_la_domanda_di_prima():
    """«Ma sei sicura?» nel vault non somiglia a niente: cercarla porta dritti
    al muro, che è il modo peggiore di rispondere a un dubbio."""
    d = "Ma sei sicura?"
    assert conversa.mossa(d, FILO_UNO) == "dubbio"
    assert conversa.query(d, FILO_UNO) == "Quanto costa il listino 2026?"


def test_prova4_il_dubbio_arriva_con_le_fonti(monkeypatch):
    visto = {}
    monkeypatch.setattr(rag, "_retrieve", lambda q, *a, **k: (visto.update(q=q), [_hit()])[1])
    monkeypatch.setattr(rag, "chat", lambda s, u: (visto.update(sys=s), "300 euro, sta scritto qui.")[1])
    r = rag.answer("Ma sei sicura?", ["forma-core"], history=FILO_UNO)
    assert visto["q"] == "Quanto costa il listino 2026?"
    assert r["sources"] and r["mossa"] == "dubbio"
    assert "torna alla fonte" in visto["sys"]
    assert "Non riformularla" in visto["sys"]


# ══════════════════════════════════════════════════════════════════════════
# PROVA 5 · silenzio, poi «allora?» → riprende dal punto dove si era fermata
# ══════════════════════════════════════════════════════════════════════════
def test_prova5_la_ripresa_riprende_il_punto():
    for d in ("allora?", "e quindi?", "continua"):
        assert conversa.mossa(d, FILO_UNO) == "ripresa", d
        assert conversa.query(d, FILO_UNO) == "Quanto costa il listino 2026?"


def test_prova5_dice_al_modello_di_non_reintrodurre():
    i = conversa.istruzione("ripresa")
    assert "RIPRENDERE" in i and "senza reintrodurre" in i


# ══════════════════════════════════════════════════════════════════════════
# Il conto delle cinque prove — quello che giustifica il punteggio dell'area
# ══════════════════════════════════════════════════════════════════════════
PROVE = {
    "torna indietro di un turno": "test_prova1_la_correzione_non_ricerca_la_frase_ritirata",
    "chiede quale invece di indovinare": "test_prova2_non_indovina_e_non_cerca",
    "abbandona senza rispondere lo stesso": "test_prova3_abbandonare_senza_niente_dopo_non_risponde_lo_stesso",
    "riapre la fonte invece di riformulare": "test_prova4_il_dubbio_arriva_con_le_fonti",
    "riprende dal punto in sospeso": "test_prova5_la_ripresa_riprende_il_punto",
}


def test_le_prove_sono_cinque_e_hanno_tutte_un_test():
    """Il punteggio della conversazione, da adesso, si legge qui. Se una prova
    sparisce dall'elenco senza che sparisca dal quadro, il quadro mente."""
    import inspect
    import sys
    qui = {n for n, _f in inspect.getmembers(sys.modules[__name__], inspect.isfunction)}
    assert len(PROVE) == 5
    for descrizione, nome in PROVE.items():
        assert nome in qui, f"«{descrizione}» non ha il suo test"


# ══════════════════════════════════════════════════════════════════════════
# C2 · Le domande che non riguardano il cervello
# ══════════════════════════════════════════════════════════════════════════
def _hit(text="Il listino 2026 parte da 300 euro.", slug="listino-2026"):
    class H:
        score = 0.9
        payload = {"text": text, "slug": slug, "title": "Listino", "tenant": "forma-core",
                   "path": "forma/docs/listino-2026.md"}
    return H()


def test_c2_una_domanda_sul_mondo_riceve_una_risposta(monkeypatch):
    """Il caso più comune di «conversazione normale», e prima non c'era un test
    che lo coprisse: la domanda non riguarda il cervello, quindi la risposta
    giusta non è né il muro né la porta — è rispondere."""
    monkeypatch.setattr(rag, "_retrieve", lambda *a, **k: [])
    monkeypatch.setattr(rag, "chat", lambda s, u: "⟦fuori⟧A New York sono le 8.⟦/fuori⟧")
    r = rag.answer("Che ore sono a New York?", ["forma-core"], free=True)
    assert "New York" in r["answer"] and r.get("free") is True
    assert "gap" not in r                       # niente offerta di annotarlo nel vault


def test_c2_non_si_offre_di_annotare_l_ora_di_new_york(monkeypatch):
    monkeypatch.setattr(rag, "_retrieve", lambda *a, **k: [])
    monkeypatch.setattr(rag, "chat", lambda s, u: "x")
    for d in ("Che ore sono a New York?", "Come si scrive un'email di sollecito?",
              "Cosa significa churn?"):
        assert conversa.generica(d), d
        assert "gap" not in rag.answer(d, ["forma-core"], free=True), d


def test_c2_una_domanda_sul_cervello_travestita_resta_una_domanda_sul_cervello(monkeypatch):
    """«Come si fa a fatturare ad ATS» ha la FORMA di una domanda generale ed è
    una domanda sul cervello. Sopprimerle l'offerta sarebbe il danno vero: il
    buco esiste e nessuno lo saprebbe."""
    assert conversa.generica("Come si fa a fatturare ad ATS?", ["ats"]) is False
    monkeypatch.setattr(rag, "_retrieve", lambda *a, **k: [])
    monkeypatch.setattr(rag, "chat", lambda s, u: "x")
    r = rag.answer("Come si fa a fatturare ad ATS?", ["forma-core", "ats"], free=True)
    assert r.get("gap")


def test_c2_il_discrimine_e_il_mondo_del_tenant_non_i_nomi_propri(monkeypatch):
    """Il primo tentativo era «se c'è un nome proprio non è generica», e cadeva
    sulla domanda dell'esempio: «New York» di nomi propri ne ha due. Il metro
    giusto è ciò di cui il cervello POTREBBE sapere qualcosa, cioè gli scope del
    tenant che sta chiedendo."""
    assert conversa.generica("Che ore sono a New York?", ["ats", "forma-core"]) is True
    assert conversa.generica("Cosa significa churn per ATS?", ["ats"]) is False


def test_c3_il_limite_non_si_muove(monkeypatch):
    """C3, di nuovo e per intero. Il tono vale per tutti; il contenuto fuori dal
    vault no. Un tenant cliente senza `libera` prende il muro anche per la
    domanda più innocua del mondo — il widget sul sito di un cliente non può
    inventare sul cliente, e questa è l'unica cosa che non si baratta per
    nessuna fluidità."""
    monkeypatch.setattr(rag, "_retrieve", lambda *a, **k: [])
    monkeypatch.setattr(rag, "chat", lambda s, u: pytest.fail("senza `libera` non si risponde"))
    r = rag.answer("Che ore sono a New York?", ["ats"], free=False)
    assert r["answer"] == rag.NO_ANSWER and r["sources"] == []


def test_le_mosse_non_allargano_i_permessi(monkeypatch):
    """Lo stesso vincolo del filo, sulle mosse nuove: ricordare che al turno
    prima si parlava di un cliente non dà il diritto di leggere le sue note."""
    visti = {}
    monkeypatch.setattr(rag, "_retrieve",
                        lambda q, grants, *a, **k: (visti.update(g=grants), [])[1])
    monkeypatch.setattr(rag, "chat", lambda s, u: "x")
    storia = [{"role": "user", "content": "Parlami di andrea-aloia e dei suoi obiettivi"},
              {"role": "assistant", "content": "Non ho accesso a quell'area."}]
    rag.answer("Ma sei sicura?", ["ats"], history=storia)
    assert visti["g"] == ["ats"]
