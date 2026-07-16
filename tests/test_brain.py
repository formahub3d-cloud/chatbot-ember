"""Cervello in console (/admin/brain*): fallback senza Supabase (persist:false,
dati vuoti, mai errori), endpoint protetti, limiti della ricerca metadati."""
from fastapi.testclient import TestClient

from app import brain, main
from app.config import settings

client = TestClient(main.app)


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
