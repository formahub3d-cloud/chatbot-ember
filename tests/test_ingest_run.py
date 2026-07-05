"""Test dell'orchestrazione di ingest.run(): swap sicuro upsert-then-prune.

Puro, senza rete: il client Qdrant, l'embed e il sync su Supabase sono mockati.
Verifica che la reindicizzazione NON azzeri mai la collection (niente
delete_collection) e che i punti orfani siano rimossi solo DOPO l'upsert, con
un filtro sul marker `ingest_run` della run corrente.
"""
from pathlib import Path
from unittest.mock import MagicMock

from app import ingest as I
from app.config import settings


def _fake_client() -> MagicMock:
    c = MagicMock()
    # ensure_collection: la collection non esiste ancora → verrà creata (mock).
    c.get_collections.return_value.collections = []
    return c


def _write_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    (vault / "forma" / "clienti" / "ats").mkdir(parents=True)
    (vault / "forma" / "clienti" / "ats" / "nota-ats.md").write_text(
        "---\ntitle: Nota ATS\n---\nContenuto ATS di prova.", "utf-8")
    (vault / "forma" / "docs").mkdir(parents=True)
    (vault / "forma" / "docs" / "doc-x.md").write_text(
        "---\ntitle: Doc X\n---\nContenuto forma-core.", "utf-8")
    return vault


def test_run_upsert_then_prune(tmp_path, monkeypatch):
    vault = _write_vault(tmp_path)
    client = _fake_client()

    monkeypatch.setattr(settings, "vault_path", str(vault))
    monkeypatch.setattr(I, "client", lambda: client)
    # embed deterministico: un vettore fittizio per ogni chunk.
    monkeypatch.setattr(I, "embed", lambda texts: [[0.0] * I.EMBED_DIM for _ in texts])
    # il sync su Supabase è best-effort: mock per non toccare la rete.
    import app.docstore as docstore
    monkeypatch.setattr(docstore, "sync_notes", lambda notes: len(notes))

    res = I.run()

    assert res["notes"] == 2
    assert res["chunks"] >= 2

    # 1) La collection NON viene mai azzerata.
    client.delete_collection.assert_not_called()

    # 2) Prima l'upsert dei punti nuovi...
    client.upsert.assert_called_once()
    _, up_kwargs = client.upsert.call_args
    points = up_kwargs["points"]
    assert points, "l'upsert deve ricevere dei punti"
    run_ids = {p.payload["ingest_run"] for p in points}
    assert len(run_ids) == 1, "tutti i punti della stessa run hanno lo stesso marker"

    # 3) ...poi la pulizia degli orfani, con filtro must_not sul marker corrente.
    client.delete.assert_called_once()
    _, del_kwargs = client.delete.call_args
    selector = del_kwargs["points_selector"]
    cond = selector.filter.must_not[0]
    assert cond.key == "ingest_run"
    assert cond.match.value == run_ids.pop()


def test_run_no_prune_when_empty(tmp_path, monkeypatch):
    """Vault senza note utili: niente upsert e — soprattutto — niente delete,
    così un vault vuoto non azzera un cervello gia' popolato."""
    vault = tmp_path / "vault"
    vault.mkdir()
    client = _fake_client()

    monkeypatch.setattr(settings, "vault_path", str(vault))
    monkeypatch.setattr(I, "client", lambda: client)
    monkeypatch.setattr(I, "embed", lambda texts: [])
    import app.docstore as docstore
    monkeypatch.setattr(docstore, "sync_notes", lambda notes: 0)

    res = I.run()

    assert res["chunks"] == 0
    client.upsert.assert_not_called()
    client.delete.assert_not_called()
    client.delete_collection.assert_not_called()
