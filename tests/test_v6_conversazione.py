"""V6 · La conversazione (B1/B2/B3) e i suoi freni, provati uno a uno.

Quello che questi test difendono non è «funziona», è **la distinzione**: il tono
vale per tutti, il contenuto fuori dal vault no. Se un domani qualcuno collega la
conoscenza generale al tono, o fa entrare una nota senza fonte, qui diventa rosso.
"""
import pytest

from app import flags, learned, proposals, rag


# ── B1 · Il muro diventa una porta ───────────────────────────────────────────

def test_il_muro_ammette_e_offre():
    """La vecchia frase chiudeva la conversazione. La nuova ammette e offre."""
    assert "Non ho questa informazione" not in rag.NO_ANSWER
    assert "non c'è" in rag.NO_ANSWER and "aggiungiamolo" in rag.NO_ANSWER.lower()
    assert "isn't in the brain" in rag._NO_ANSWER_EN


def test_il_system_prompt_impone_la_frase_nuova():
    """Il modello deve emetterla ALLA LETTERA: è così che la console la
    riconosce e ci attacca il bottone."""
    assert rag.NO_ANSWER in rag._system("it")
    assert rag._NO_ANSWER_EN in rag._system("en")


def test_gap_viaggia_con_la_risposta(monkeypatch):
    """Senza contenuto la risposta porta `gap`: la console ci attacca l'offerta
    di scrivere la nota, nella bolla — non in un menu altrove."""
    monkeypatch.setattr(rag, "_retrieve", lambda *a, **k: [])
    out = rag.answer("una domanda che il cervello non sa", ["ats"])
    assert out["answer"] == rag.NO_ANSWER
    assert out["gap"]["question"] == "una domanda che il cervello non sa"
    assert out["gap"]["offer"] == rag.gap_offer("it")


def test_gap_redatto_dai_dati_personali(monkeypatch):
    """La domanda torna indietro come TITOLO pronto da salvare: se conteneva un
    IBAN, non deve rientrare nel vault passando di lì."""
    monkeypatch.setattr(rag, "_retrieve", lambda *a, **k: [])
    out = rag.answer("mandare a mario@example.com il saldo", ["ats"])
    assert "mario@example.com" not in out["gap"]["question"]
    assert "[email]" in out["gap"]["question"]


def test_gap_anche_nello_stream(monkeypatch):
    monkeypatch.setattr(rag, "_retrieve", lambda *a, **k: [])
    ev = "".join(rag.answer_stream("boh", ["ats"]))
    assert '"gap"' in ev and "offer" in ev


def test_risposta_con_contenuto_non_ha_gap(monkeypatch):
    """Quando il cervello sa, non c'è nessun buco da offrire di colmare."""
    class H:
        score = 0.9
        payload = {"slug": "nota", "title": "Nota", "text": "il contenuto"}
    monkeypatch.setattr(rag, "_retrieve", lambda *a, **k: [H()])
    monkeypatch.setattr(rag, "chat_con_uso", lambda s, u: ("la risposta", None))
    assert "gap" not in rag.answer("q", ["ats"])


# ── B2 · Il tono vale per tutti, il contenuto fuori dal vault no ─────────────

def test_il_tono_e_per_tutti():
    """Nessun parametro lo accende: c'è per owner e per clienti allo stesso modo."""
    for lang in ("it", "en"):
        for tier in (None, "dante", "beatrice"):
            assert "TONE" in rag._system(lang, tier) or "MODO DI PARLARE" in rag._system(lang, tier)


def test_il_tono_non_e_un_permesso_sui_dati():
    """Lo strato di tono NON deve contenere la deroga: il vincolo «solo dal
    CONTENUTO» resta scritto, e la deroga arriva solo con free=True."""
    base = rag._system("it")
    assert "DEROGA TITOLARE" not in base and "⟦fuori⟧" not in base
    assert "esclusivamente dal CONTENUTO" in base
    assert "DEROGA TITOLARE" in rag._system("it", free=True)


def test_libera_e_un_flag_del_record_non_della_richiesta():
    flags.reset()
    assert flags.libera("ats") is False              # default = il freno
    assert flags.set_libera("ats", True, "Andrea") is True
    assert flags.libera("ats") is True
    assert flags.libera("hrh") is False              # non contagia gli altri tenant
    flags.reset()


def test_libera_richiede_la_firma():
    flags.reset()
    assert flags.set_libera("ats", True, "") is False
    assert flags.libera("ats") is False
    flags.reset()


def test_due_flag_sullo_stesso_tenant_convivono():
    """Regressione: con l'assegnazione secca, accendere `libera` spegneva `liv3`."""
    flags.reset()
    flags.set_liv3("ats", True, "Andrea")
    flags.set_libera("ats", True, "Andrea")
    assert flags.liv3("ats") is True and flags.libera("ats") is True
    flags.reset()


# ── B3 · Le conversazioni propongono note, non le scrivono ──────────────────

CONV = ("Utente: fate il ritiro a domicilio anche fuori città?\n"
        "Divina: no, fuori dal centro il ritiro non lo facciamo, si passa dal punto di raccolta")


def _voce(**kw):
    v = {"titolo": "Ritiro solo in centro", "contenuto": "Fuori dal centro si usa il punto di raccolta.",
         "citazione": "fuori dal centro il ritiro non lo facciamo"}
    v.update(kw)
    return v


def test_una_proposta_senza_fonte_non_passa():
    """Regola 2 · Un modello che «cita» ricostruendo a memoria è il modo esatto
    in cui una voce di corridoio diventa una nota."""
    assert learned.filtra([_voce()], CONV, "ats")
    assert learned.filtra([_voce(citazione="una frase che nessuno ha mai detto qui")], CONV, "ats") == []
    assert learned.filtra([_voce(citazione="")], CONV, "ats") == []
    assert learned.filtra([_voce(citazione="troppo corta")], CONV, "ats") == []


def test_la_citazione_tollera_spazi_e_virgolette_ma_resta_letterale():
    assert learned.filtra([_voce(citazione="  Fuori dal Centro il ritiro NON lo facciamo ")], CONV, "ats")


def test_i_dati_personali_si_scartano_non_si_redigono():
    """Regola 3 · Una nota con «[email]» dentro è peggio di una nota assente."""
    conv = CONV + "\nUtente: scrivimi a mario@example.com"
    assert learned.filtra([_voce(contenuto="Scrivere a mario@example.com")], conv, "ats") == []
    assert learned.filtra([_voce(titolo="Contatto: mario@example.com")], conv, "ats") == []


def test_mai_verso_la_scheda_personale():
    """`andrea-aloia/human/` è fuori dall'indice per scelta: nessuna proposta
    può indirizzarsi lì."""
    for scope in ("human", "andrea-aloia/human", ""):
        assert learned.filtra([_voce()], CONV, scope) == []


def test_al_massimo_tre():
    voci = [_voce(titolo=f"Cosa {i}") for i in range(9)]
    assert len(learned.filtra(voci, CONV, "ats")) == learned.MAX_ITEMS


def test_zero_e_una_risposta_giusta():
    assert learned.filtra([], CONV, "ats") == []
    assert learned.proponi([{"role": "user", "content": "ciao"}], "ats") == []   # sotto MIN_TURNS


def test_proponi_non_scrive_mai(monkeypatch):
    """Il modulo ritorna candidati: la scrittura resta il write-back a due tempi."""
    monkeypatch.setattr(learned, "chat", lambda s, u: '{"imparato": [' +
                        '{"titolo":"Ritiro solo in centro","contenuto":"Punto di raccolta.",'
                        '"citazione":"fuori dal centro il ritiro non lo facciamo"}]}')
    out = learned.proponi([{"role": "user", "content": "fate il ritiro a domicilio anche fuori città?"},
                           {"role": "assistant", "content": "no, fuori dal centro il ritiro non lo "
                                                            "facciamo, si passa dal punto di raccolta"}], "ats")
    assert len(out) == 1 and out[0]["scope"] == "ats"
    assert out[0]["citazione"]


def test_modello_muto_o_rotto_non_propone_niente(monkeypatch):
    storia = [{"role": "user", "content": "a" * 30}, {"role": "assistant", "content": "b" * 30}]
    monkeypatch.setattr(learned, "chat", lambda s, u: "mi spiace, non sono JSON")
    assert learned.proponi(storia, "ats") == []
    monkeypatch.setattr(learned, "chat", lambda s, u: (_ for _ in ()).throw(RuntimeError("giù")))
    assert learned.proponi(storia, "ats") == []


def test_in_coda_non_significa_salvato():
    """`add_learned` mette in coda e basta: la nota nasce dall'approvazione."""
    proposals.reset()
    fuori = proposals.add_learned([_voce(scope="ats")], conversazione="chat console")
    assert len(fuori) == 1 and fuori[0]["source"] == "conversazione"
    assert fuori[0]["citazione"] and fuori[0]["nota_titolo"] == "Ritiro solo in centro"
    ids = [p["id"] for p in proposals.generate()]
    assert fuori[0]["id"] in ids
    proposals.reset()


def test_la_stessa_cosa_non_si_accoda_due_volte():
    proposals.reset()
    proposals.add_learned([_voce(scope="ats")])
    assert proposals.add_learned([_voce(scope="ats")]) == []
    assert len([p for p in proposals.generate() if p["source"] == "conversazione"]) == 1
    proposals.reset()


def test_ignorare_una_proposta_da_conversazione_la_fa_sparire():
    proposals.reset()
    p = proposals.add_learned([_voce(scope="ats")])[0]
    proposals.dismiss(p["id"])
    assert p["id"] not in [x["id"] for x in proposals.generate()]
    proposals.reset()


def test_approvare_scrive_la_nota_marcata(monkeypatch, tmp_path):
    """Approvata → nota nel vault, marcata come nata da conversazione, con la
    citazione dentro. È la conferma umana della regola #4."""
    from app import writeback
    from app.config import settings
    monkeypatch.setattr(settings, "vault_path", str(tmp_path))
    proposals.reset()
    p = proposals.add_learned([_voce(scope="ats")])[0]
    res = proposals.approve(p["id"])
    assert res and res["kind"] == "conversazione"
    testo = (tmp_path / res["nota"]["path"]).read_text("utf-8")
    assert "NON verificato" in testo and "Origine: conversazione" in testo
    assert "fuori dal centro il ritiro non lo facciamo" in testo   # la fonte viaggia con la nota
    assert p["id"] not in [x["id"] for x in proposals.generate()]
    proposals.reset()


def test_se_la_scrittura_fallisce_la_proposta_resta(monkeypatch):
    """Mai un «fatto» senza il fatto: se la nota non nasce, la proposta torna."""
    from app import writeback
    proposals.reset()
    p = proposals.add_learned([_voce(scope="ats")])[0]
    monkeypatch.setattr(writeback, "save_note",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("disco pieno")))
    assert proposals.approve(p["id"]) is None
    assert p["id"] in [x["id"] for x in proposals.generate()]
    proposals.reset()
