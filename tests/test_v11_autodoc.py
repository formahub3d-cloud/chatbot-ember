"""V11/D · Divina sa come funziona, e lo sa dal vault — non dal codice.

L'idea è di Andrea: «Divina deve sapere come funziona e come si può migliorare.
Non devi saperlo solo tu, ma anche lei.» Oggi sa tutto dei clienti di FORMA e
niente di sé stessa: se le chiedono «cosa puoi fare per la mia azienda?»
risponde da istruzioni scritte nel codice, cioè da qualcosa che nessuno può
leggere, correggere o citare.
"""
import pytest

from app import autodoc, rag
from app.config import settings


@pytest.fixture()
def vault(tmp_path, monkeypatch):
    d = tmp_path / "ovyon" / "divina"
    d.mkdir(parents=True)
    (d / "01-cosa-so-fare.md").write_text(
        "---\ntitle: Divina — cosa so fare\n---\n\n# Cosa so fare\n\n"
        "Rispondo con le note dell'azienda, e dico da dove viene ogni risposta.\n", "utf-8")
    (d / "02-come-mi-alimenti.md").write_text(
        "---\ntitle: Divina — come mi alimenti\n---\n\nCorreggermi è la via più veloce.\n", "utf-8")
    monkeypatch.setattr(settings, "vault_path", str(tmp_path))
    return tmp_path


def test_le_note_si_leggono_col_loro_titolo(vault):
    n = autodoc.note()
    assert [x["title"] for x in n] == ["Divina — cosa so fare", "Divina — come mi alimenti"]
    assert "---" not in n[0]["text"]                    # frontmatter fuori
    assert n[0]["path"] == "ovyon/divina/01-cosa-so-fare.md"


def test_l_ordine_lo_decide_chi_scrive_non_il_filesystem(vault):
    assert [x["slug"] for x in autodoc.note()] == ["01-cosa-so-fare", "02-come-mi-alimenti"]


def test_riconosce_le_domande_su_di_se():
    for d in ("cosa puoi fare per la mia azienda?", "come faccio a migliorarti?",
              "come funzioni?", "chi sei?", "cosa NON sai fare?"):
        assert autodoc.e_su_di_se(d), d


def test_non_ruba_le_domande_degli_altri():
    """Un riconoscitore che si prende «cosa sai di ATS» farebbe sparire il
    retrieval vero. Serve il soggetto: senza, la domanda non parla di lei."""
    for d in ("cosa sai di ATS?", "quanto costa il listino?",
              "come si fa a fatturare?", "parlami dei clienti"):
        assert not autodoc.e_su_di_se(d), d


def test_risponde_citando_le_note_del_vault(vault, monkeypatch):
    """Il punto del blocco: la risposta ha una FONTE, apribile e correggibile.
    Prima veniva da istruzioni nel codice, che nessuno può citare."""
    monkeypatch.setattr(rag, "_retrieve",
                        lambda *a, **k: pytest.fail("le note si leggono dal disco"))
    monkeypatch.setattr(rag, "chat", lambda s, u: "Rispondo con le note della tua azienda.")
    r = rag.answer("Cosa puoi fare per la mia azienda?", ["ats"])
    assert r["autodoc"] is True
    assert [s["path"] for s in r["sources"]] == ["ovyon/divina/01-cosa-so-fare.md",
                                                 "ovyon/divina/02-come-mi-alimenti.md"]


def test_le_note_arrivano_anche_a_un_tenant_senza_lo_scope_ovyon(vault, monkeypatch):
    """Sono pubbliche per natura: è quello che si racconta in una demo. Il
    canale è in sola lettura e su UNA cartella fissa — non passa dal filtro e
    non lo tocca, perché spostare una decisione di sicurezza dentro un problema
    di prodotto è il modo in cui i permessi si allargano per sbaglio."""
    monkeypatch.setattr(rag, "chat", lambda s, u: "ok")
    assert rag.answer("Chi sei?", ["ats"]).get("autodoc") is True
    assert rag.answer("Chi sei?", ["forma-core"]).get("autodoc") is True


def test_la_cartella_non_e_un_parametro():
    """Un percorso che arriva dalla richiesta è il modo classico di leggere
    /etc/passwd. Qui è una costante, e questo test esiste perché resti tale."""
    import inspect
    assert "CARTELLA" in inspect.getsource(autodoc._dir)
    assert autodoc.CARTELLA == ("ovyon", "divina")


def test_senza_le_note_non_inventa_una_risposta_di_circostanza(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "vault_path", str(tmp_path))
    assert autodoc.contesto("chi sei?") is None
    assert autodoc.note() == []


# ── D2 · il percorso, non solo lo stato ─────────────────────────────────────
def test_dice_a_che_punto_e_il_lavoro_con_un_cliente():
    r = autodoc.punto_del_lavoro("ats", [{"title": "Servizi", "text": "impianti e manutenzione"}],
                                 proposte=2)
    assert "una voce" in r["racconto"]
    assert "orari" in r["racconto"] and "prezzi" in r["racconto"]
    assert "2 proposte" in r["racconto"]
    assert set(r["mancano"]) >= {"orari", "prezzi"}


def test_dice_la_conseguenza_non_solo_il_buco():
    """«Mancano gli orari» è un fatto; «finché non ci sono, a chi lo chiede il
    bot risponde che non lo sa» è il motivo per cui uno si muove."""
    r = autodoc.punto_del_lavoro("hrh", [])
    assert "vuota" in r["racconto"] and "non lo sa" in r["racconto"]


def test_una_kb_completa_non_si_lamenta():
    piene = [{"title": "Orari e prezzi", "text": "contatti, servizi, domande frequenti"}]
    r = autodoc.punto_del_lavoro("ats", piene)
    assert r["mancano"] == [] and "Mancano" not in r["racconto"]
