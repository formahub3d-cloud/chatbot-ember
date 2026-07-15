"""Roadmap del cervello (/admin/roadmap): payload statico versionato nel repo,
campi obbligatori per ogni task, conteggi coerenti, endpoint protetto."""
from fastapi.testclient import TestClient

from app import main, roadmap
from app.config import settings

client = TestClient(main.app)

_CAMPI = {"id", "area", "priority", "status", "effort", "repo",
          "title", "description", "zoey_ref", "divina_note"}
_PRIORITY = {"alta", "media", "bassa"}
_STATUS = {"da-fare", "parziale", "in-corso", "fatto"}
_REPO = {"motore", "orchestratore", "entrambi"}


def test_task_ben_formate():
    out = roadmap.roadmap()
    assert out["tasks"], "la roadmap non può essere vuota"
    ids = [t["id"] for t in out["tasks"]]
    assert len(ids) == len(set(ids)), "id duplicati"
    for t in out["tasks"]:
        assert _CAMPI <= set(t), f"campi mancanti in {t.get('id')}"
        assert t["priority"] in _PRIORITY
        assert t["status"] in _STATUS
        assert t["repo"] in _REPO
        assert t["effort"] in {"S", "M", "L"}


def test_conteggi_coerenti():
    out = roadmap.roadmap()
    c = out["counts"]
    assert c["totale"] == len(out["tasks"])
    assert c["aperte"] + c["parziali"] + c["fatte"] == c["totale"]
    assert out["benchmark"]["name"] == "Zoey OS"
    assert out["strengths"], "i punti di forza documentano cosa NON barattare"


def test_endpoint_admin_roadmap(monkeypatch):
    monkeypatch.setattr(settings, "admin_token", "SEG")
    assert client.get("/admin/roadmap").status_code == 401
    r = client.get("/admin/roadmap", headers={"Authorization": "Bearer SEG"})
    assert r.status_code == 200
    body = r.json()
    assert body["counts"]["totale"] == len(body["tasks"])
    assert any(t["area"] == "memoria" for t in body["tasks"])
