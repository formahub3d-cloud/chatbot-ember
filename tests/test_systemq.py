"""Fase 6 + task 16 · «Dimmi cosa sai» risponde dall'indice, i saluti non
trovano il muro. Riconoscitori PRUDENTI: il falso positivo (un collage al
posto di una risposta) è peggio del falso negativo (retrieval normale).
"""
import pytest

from app import rag, systemq


# ── saluti: match sull'INTERA frase, mai su un pezzo ─────────────────────────
@pytest.mark.parametrize("q,tipo", [
    ("ciao", "saluto"), ("Ciao!", "saluto"), ("buongiorno divina", "saluto"),
    ("come va?", "come-stai"), ("grazie mille", "grazie"),
    ("chi sei?", "chi-sei"), ("ci sei?", "ci-sei"), ("a presto", "congedo"),
])
def test_saluti_riconosciuti(q, tipo):
    assert systemq.saluto(q) == tipo


@pytest.mark.parametrize("q", [
    "ciao, quanto costa la stampa 3d?",         # saluto + contenuto → contenuto
    "buongiorno, vorrei il listino",
    "grazie, e i tempi di consegna?",
    "chi sei tu per dirmi i prezzi",
    "quali servizi offre FORMA?",
])
def test_saluti_non_scattano_sul_contenuto(q):
    assert systemq.saluto(q) is None


# ── domande sul sistema ──────────────────────────────────────────────────────
@pytest.mark.parametrize("q,tipo", [
    ("dimmi cosa sai", "cosa-sai"), ("cosa sai?", "cosa-sai"),
    ("che cosa conosci", "cosa-sai"), ("cosa c'è nel tuo cervello?", "cosa-sai"),
    ("quante note hai?", "quante"), ("quali clienti conosci?", "clienti"),
    ("quando ti sei aggiornata?", "aggiornamento"), ("cosa non sai?", "buchi"),
])
def test_domande_sistema_riconosciute(q, tipo):
    ds = systemq.domanda_sistema(q)
    assert ds is not None and ds[0] == tipo


@pytest.mark.parametrize("q", [
    "cosa sai dirmi sui prezzi della stampa?",   # «sai dirmi» = contenuto
    "sai se siete aperti sabato?",
    "sai quanto costa la resina?",
    "mi sai dire dove siete?",
    "vorrei sapere cosa fate",
])
def test_domande_contenuto_non_intercettate(q):
    assert systemq.domanda_sistema(q) is None


def test_cosa_sai_di_cliente_visibile(monkeypatch):
    monkeypatch.setattr(systemq, "quadro", lambda g: {
        "scopes": {"ats": 12, "forma-core": 50}, "aggiornato": "2026-07-31"})
    out = systemq.rispondi_sistema("di", "ATS", ["ats", "forma-core"])
    assert "12 note" in out and "2026-07-31" in out


def test_cosa_sai_di_argomento_ignoto_va_al_retrieval(monkeypatch):
    """«cosa sai di <argomento>» con argomento che NON è un'area visibile:
    è una domanda di CONTENUTO → None → retrieval normale. Mai un collage."""
    monkeypatch.setattr(systemq, "quadro", lambda g: {
        "scopes": {"ats": 12}, "aggiornato": ""})
    assert systemq.rispondi_sistema("di", "stampa 3d", ["ats"]) is None
    assert systemq.intercetta("cosa sai della stampa 3d?", ["ats"]) is None


def test_cosa_sai_elenca_aree_e_buchi(monkeypatch):
    monkeypatch.setattr(systemq, "quadro", lambda g: {
        "scopes": {"forma-core": 50, "ats": 12, "hrh": 0}, "aggiornato": "2026-07-31"})
    out = systemq.rispondi_sistema("cosa-sai", None, ["*"])
    assert "forma-core: 50 note" in out and "ats: 12 note" in out
    assert "62" in out                        # totale
    buchi = systemq.rispondi_sistema("buchi", None, ["*"])
    assert "hrh" in buchi                     # dire cosa non si sa è metà del valore


# ── l'aggancio in rag: il percorso sistema NON tocca il retrieval ────────────
def test_answer_intercetta_senza_retrieval(monkeypatch):
    chiamato = {"retrieve": False}
    monkeypatch.setattr(rag, "_retrieve",
                        lambda *a, **k: chiamato.update(retrieve=True) or [])
    monkeypatch.setattr(systemq, "quadro", lambda g: {
        "scopes": {"ats": 3}, "aggiornato": "2026-07-31"})
    r = rag.answer("dimmi cosa sai", ["ats"])
    assert r.get("system") is True and r["sources"] == []
    assert "ats: 3 note" in r["answer"]
    assert chiamato["retrieve"] is False      # percorso DIVERSO, non recupero migliore


def test_answer_saluto_cortese_senza_muro(monkeypatch):
    chiamato = {"retrieve": False}
    monkeypatch.setattr(rag, "_retrieve",
                        lambda *a, **k: chiamato.update(retrieve=True) or [])
    r = rag.answer("ciao", ["ats"])
    assert r.get("system") is True
    assert "non ho questa informazione" not in r["answer"].lower()
    assert chiamato["retrieve"] is False


def test_answer_stream_intercetta(monkeypatch):
    monkeypatch.setattr(rag, "_retrieve", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("il retrieval non va chiamato per una domanda di sistema")))
    monkeypatch.setattr(systemq, "quadro", lambda g: {"scopes": {"ats": 3}, "aggiornato": ""})
    out = "".join(rag.answer_stream("quante note hai?", ["ats"]))
    assert "system" in out and "ats: 3 note" in out and "done" in out


def test_contenuto_normale_passa_dal_retrieval(monkeypatch):
    """Fallback esplicito: una domanda di contenuto va al retrieval come sempre."""
    chiamato = {"retrieve": False}
    monkeypatch.setattr(rag, "_retrieve",
                        lambda *a, **k: chiamato.update(retrieve=True) or [])
    r = rag.answer("quanto costa la stampa 3d?", ["ats"])
    assert chiamato["retrieve"] is True
    assert "system" not in r
