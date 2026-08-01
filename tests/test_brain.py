"""Cervello in console (/admin/brain*): fallback senza Supabase (persist:false,
dati vuoti, mai errori), endpoint protetti, limiti della ricerca metadati."""
from fastapi.testclient import TestClient

from app import brain, main
from app.config import settings

client = TestClient(main.app)


def setup_function(_):
    brain.reset()


def _h():
    return {"Authorization": "Bearer SEG"}


def test_fallback_senza_supabase():
    # nei test il backend è statico → tutto vuoto ma con la shape giusta, zero errori
    assert brain.enabled() is False
    s = brain.stats()
    assert s == {"notes": 0, "areas": 0, "recent_7d": 0, "last_ingest": None, "by_tenant": {}}
    assert brain.notes() == []
    assert brain.notes("qualunque", limit=9999) == []


def test_endpoints_protetti_e_shape(monkeypatch):
    monkeypatch.setattr(settings, "admin_token", "SEG")
    assert client.get("/admin/brain").status_code == 401
    assert client.get("/admin/brain/notes").status_code == 401
    b = client.get("/admin/brain", headers=_h()).json()
    assert b["persist"] is False and b["stats"]["notes"] == 0 and b["recent"] == []
    n = client.get("/admin/brain/notes?q=stampa&limit=5", headers=_h()).json()
    assert n == {"notes": [], "persist": False}


def test_build_graph_dai_wikilink():
    notes = [
        {"slug": "a", "title": "A", "tenant": "forma-core",
         "content": "vedi [[b|Bella]] e [[c#sezione]], poi [[A]] e [[x-inesistente]]"},
        {"slug": "b", "title": "B", "tenant": "ats", "content": "torna ad [[A]]"},
        {"slug": "c", "title": "C", "tenant": "forma-core", "content": ""},
    ]
    g = brain.build_graph(notes)
    assert [n["slug"] for n in g["nodes"]] == ["a", "b", "c"]
    # alias e ancore risolti; self-link scartato; inesistente ignorato;
    # a↔b contato UNA volta (b→[[A]] è lo stesso arco non orientato)
    assert sorted(g["links"]) == [[0, 1], [0, 2]]
    assert g["generated_at"].endswith("Z")


def test_save_graph_fallback_e_endpoint(monkeypatch):
    monkeypatch.setattr(settings, "admin_token", "SEG")
    assert client.get("/admin/brain/graph").status_code == 401
    assert client.get("/admin/brain/graph", headers=_h()).status_code == 404
    n = brain.save_graph([
        {"slug": "a", "title": "A", "tenant": "forma-core", "content": "[[b]]"},
        {"slug": "b", "title": "B", "tenant": "ats", "content": ""},
    ])
    assert n == 1
    body = client.get("/admin/brain/graph", headers=_h()).json()
    assert body["persist"] is False and body["links"] == [[0, 1]]
    assert [x["slug"] for x in body["nodes"]] == ["a", "b"]


# ── V5b · Punto 9: il commit dell'ultima ingest, per l'allarme che confronta ──
def test_ingest_commit_registrato_ed_esposto(monkeypatch):
    monkeypatch.setattr(settings, "admin_token", "SEG")
    # mai registrato (motore vecchio / tabella assente) → None, e il pannello
    # torna al confronto sulle ore invece di fingere un allineamento
    assert brain.ingest_commit() is None
    b = client.get("/admin/brain", headers=_h()).json()
    assert b["ingest_commit"] is None
    # registrato → {vault_commit, at} in /admin/brain, pronto per il confronto
    brain.set_ingest_commit("1f73289abc12")
    b = client.get("/admin/brain", headers=_h()).json()
    assert b["ingest_commit"]["vault_commit"] == "1f73289abc12"
    assert b["ingest_commit"]["at"].endswith("Z")
    # vuoto = no-op: un commit illeggibile non deve cancellare l'ultimo vero
    brain.set_ingest_commit("")
    assert brain.ingest_commit()["vault_commit"] == "1f73289abc12"
