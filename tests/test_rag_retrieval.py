"""Filtro di rilevanza del retrieval: da un pool ordinato, tiene i chunk sopra la
soglia (relativa al migliore + assoluta) e limita a k. Nessuna rete: usa hit finti."""
from types import SimpleNamespace

from app import rag
from app.config import settings


def _hits(scores):
    return [SimpleNamespace(score=s, payload={}) for s in scores]


def _h(score, slug):
    return SimpleNamespace(score=score, payload={"slug": slug})


def test_soglia_relativa_scarta_la_coda(monkeypatch):
    monkeypatch.setattr(settings, "retrieval_rel_score", 0.5)
    monkeypatch.setattr(settings, "retrieval_min_score", 0.0)
    kept = rag._filter_hits(_hits([0.9, 0.7, 0.4, 0.2]), k=6)
    assert [h.score for h in kept] == [0.9, 0.7]      # soglia = 0.45


def test_k_limita_i_risultati(monkeypatch):
    monkeypatch.setattr(settings, "retrieval_rel_score", 0.0)
    monkeypatch.setattr(settings, "retrieval_min_score", 0.0)
    kept = rag._filter_hits(_hits([0.9, 0.8, 0.7, 0.6, 0.5]), k=3)
    assert [h.score for h in kept] == [0.9, 0.8, 0.7]


def test_soglia_assoluta_puo_dire_non_lo_so(monkeypatch):
    monkeypatch.setattr(settings, "retrieval_min_score", 0.95)
    monkeypatch.setattr(settings, "retrieval_rel_score", 0.0)
    assert rag._filter_hits(_hits([0.9, 0.8]), k=6) == []   # niente sopra 0.95


def test_nessun_hit():
    assert rag._filter_hits([], k=6) == []


def test_default_tiene_almeno_il_migliore(monkeypatch):
    monkeypatch.setattr(settings, "retrieval_rel_score", 0.5)
    monkeypatch.setattr(settings, "retrieval_min_score", 0.0)
    kept = rag._filter_hits(_hits([0.3, 0.1]), k=6)
    assert kept and kept[0].score == 0.3                    # il top passa sempre


def test_diversita_una_per_nota(monkeypatch):
    monkeypatch.setattr(settings, "retrieval_rel_score", 0.0)
    monkeypatch.setattr(settings, "retrieval_min_score", 0.0)
    monkeypatch.setattr(settings, "retrieval_per_note", 1)
    hits = [_h(0.9, "a"), _h(0.85, "a"), _h(0.8, "b"), _h(0.7, "c")]
    kept = rag._filter_hits(hits, k=3)
    assert [h.payload["slug"] for h in kept] == ["a", "b", "c"]   # codas di "a" scartate


def test_diversita_riempie_se_poche_note(monkeypatch):
    monkeypatch.setattr(settings, "retrieval_rel_score", 0.0)
    monkeypatch.setattr(settings, "retrieval_min_score", 0.0)
    monkeypatch.setattr(settings, "retrieval_per_note", 1)
    hits = [_h(0.9, "a"), _h(0.85, "a"), _h(0.8, "a")]
    kept = rag._filter_hits(hits, k=2)
    assert len(kept) == 2                                        # nessuno slot sprecato


def test_diversita_off_torna_topk(monkeypatch):
    monkeypatch.setattr(settings, "retrieval_rel_score", 0.0)
    monkeypatch.setattr(settings, "retrieval_min_score", 0.0)
    monkeypatch.setattr(settings, "retrieval_per_note", 0)
    hits = [_h(0.9, "a"), _h(0.85, "a"), _h(0.8, "b")]
    assert [h.payload["slug"] for h in rag._filter_hits(hits, k=2)] == ["a", "a"]
