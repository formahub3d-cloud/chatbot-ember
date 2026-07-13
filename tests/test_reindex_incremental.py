"""Re-ingest INCREMENTALE (Fase 5 / connettore realtime): re-indicizza solo le note
toccate senza azzerare la collection; endpoint /ingest con `paths`; auto-reingest
opzionale dopo il write-back. Tutto offline (Qdrant + embeddings mockati)."""
import pytest
from fastapi.testclient import TestClient

from app import ingest, main
from app.config import settings

client = TestClient(main.app)


class FakeQ:
    """Finto client Qdrant: registra upsert e delete."""
    def __init__(self):
        self.upserts = []      # list[list[PointStruct]]
        self.deletes = []      # list[selector]

    def upsert(self, coll, points=None, wait=False):
        self.upserts.append(points)

    def delete(self, coll, points_selector=None, wait=False):
        self.deletes.append(points_selector)


def _wire(monkeypatch, tmp_path, fq):
    monkeypatch.setattr(settings, "vault_path", str(tmp_path))
    monkeypatch.setattr(ingest, "client", lambda: fq)
    monkeypatch.setattr(ingest, "ensure_collection", lambda c, fresh=False: None)
    monkeypatch.setattr(ingest, "embed", lambda chunks: [[0.1, 0.2, 0.3] for _ in chunks])
    monkeypatch.setattr(ingest, "sync_vault", lambda *a, **k: False)
    import app.docstore as ds
    monkeypatch.setattr(ds, "sync_notes", lambda notes: len(notes))


def _note(tmp_path, rel, body="Corpo della nota con contenuto reale."):
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"---\ntitle: Nota Test\ntags: [x]\n---\n\n{body}\n", "utf-8")
    return rel


def test_reindex_una_nota_cancella_e_ricarica(monkeypatch, tmp_path):
    fq = FakeQ()
    _wire(monkeypatch, tmp_path, fq)
    rel = _note(tmp_path, "forma/clienti/ats/kb-ats.md")
    out = ingest.reindex_paths([rel])
    assert out["mode"] == "incremental" and out["indexed"] == 1 and out["removed"] == 0
    assert out["chunks"] >= 1
    # ha PRIMA cancellato i punti della nota (per path) e POI ricaricato
    assert len(fq.deletes) == 1 and len(fq.upserts) == 1
    pts = fq.upserts[0]
    assert pts and pts[0].payload["path"] == "forma/clienti/ats/kb-ats.md"
    assert pts[0].payload["tenant"] == "ats"           # scope corretto dal path
    # niente azzeramento della collection (fresh=True mai usato → ensure_collection mockato)


def test_reindex_nota_sparita_solo_rimozione(monkeypatch, tmp_path):
    fq = FakeQ()
    _wire(monkeypatch, tmp_path, fq)
    out = ingest.reindex_paths(["forma/clienti/ats/non-esiste.md"])
    assert out["indexed"] == 0 and out["removed"] == 1
    assert len(fq.deletes) == 1 and len(fq.upserts) == 0   # cancella, non carica


def test_reindex_ignora_path_fuori_vault(monkeypatch, tmp_path):
    fq = FakeQ()
    _wire(monkeypatch, tmp_path, fq)
    out = ingest.reindex_paths(["../../etc/passwd", "/abs/x.md"])
    assert out["indexed"] == 0 and out["removed"] == 0
    assert fq.deletes == [] and fq.upserts == []           # nessuna azione


def test_ingest_endpoint_paths_incrementale(monkeypatch):
    monkeypatch.setattr(settings, "admin_token", "SEG")
    seen = {}
    monkeypatch.setattr(ingest, "reindex_paths",
                        lambda paths, **k: seen.update(paths=paths) or {"mode": "incremental", "indexed": len(paths)})
    monkeypatch.setattr(ingest, "run", lambda: seen.update(full=True) or {"mode": "full"})
    r = client.post("/ingest", headers={"Authorization": "Bearer SEG"},
                    json={"paths": ["forma/clienti/ats/kb-ats.md"]})
    assert r.status_code == 200 and r.json()["mode"] == "incremental"
    assert seen["paths"] == ["forma/clienti/ats/kb-ats.md"] and "full" not in seen


def test_ingest_endpoint_senza_body_fa_ingest_completo(monkeypatch):
    monkeypatch.setattr(settings, "admin_token", "SEG")
    seen = {}
    monkeypatch.setattr(ingest, "run", lambda: seen.update(full=True) or {"mode": "full"})
    monkeypatch.setattr(ingest, "reindex_paths", lambda *a, **k: seen.update(inc=True) or {})
    r = client.post("/ingest", headers={"Authorization": "Bearer SEG"})
    assert r.status_code == 200 and r.json()["mode"] == "full"
    assert seen.get("full") and "inc" not in seen


def test_ingest_endpoint_auth(monkeypatch):
    monkeypatch.setattr(settings, "admin_token", "SEG")
    assert client.post("/ingest", headers={"Authorization": "Bearer NO"}).status_code == 401
