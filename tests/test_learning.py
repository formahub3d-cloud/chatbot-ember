"""Task di apprendimento (/admin/learning): raggruppamento gap+feedback per
scope/domanda normalizzata, conteggio, ordinamento e suggerimenti. In-memory."""
from fastapi.testclient import TestClient

from app import main, metrics
from app.config import settings

client = TestClient(main.app)


def setup_function(_):
    metrics.reset()


def test_norm_q():
    assert metrics._norm_q("Quanto costa, la Stampa 3D?!") == "quanto costa la stampa 3d"
    assert metrics._norm_q("  Quanto   costa la stampa 3d ") == "quanto costa la stampa 3d"
    assert metrics._norm_q("") == ""


def test_raggruppa_varianti_stessa_domanda():
    metrics.bump_gap(["ats"], "Quanto costa la stampa 3D?")
    metrics.bump_gap(["ats"], "quanto costa la stampa 3d")
    metrics.bump_gap(["ats"], "QUANTO COSTA LA STAMPA 3D!!")
    out = metrics.learning_tasks()
    assert len(out["tasks"]) == 1
    t = out["tasks"][0]
    assert t["kind"] == "gap" and t["scope"] == "ats" and t["count"] == 3
    assert "ats" in t["suggestion"] and "ingest" in t["suggestion"]
    assert out["generated_at"].endswith("Z")


def test_ordina_per_frequenza_e_separa_scope():
    metrics.bump_gap(["ats"], "domanda rara")
    metrics.bump_gap(["forma-core"], "domanda frequente")
    metrics.bump_gap(["forma-core"], "domanda frequente")
    metrics.bump_feedback(["hrh"], up=False, question="risposta debole")
    metrics.bump_feedback(["hrh"], up=True, question="ok")   # i 👍 non generano task
    out = metrics.learning_tasks()
    kinds = [(t["kind"], t["scope"], t["count"]) for t in out["tasks"]]
    assert kinds[0] == ("gap", "forma-core", 2)              # il più frequente in testa
    assert ("feedback", "hrh", 1) in kinds
    assert len(out["tasks"]) == 3
    fb = next(t for t in out["tasks"] if t["kind"] == "feedback")
    assert "👎" in fb["suggestion"]


def test_endpoint_admin_learning(monkeypatch):
    monkeypatch.setattr(settings, "admin_token", "SEG")
    metrics.bump_gap(["ats"], "che orari fate?")
    assert client.get("/admin/learning").status_code == 401
    r = client.get("/admin/learning", headers={"Authorization": "Bearer SEG"})
    assert r.status_code == 200
    body = r.json()
    assert body["tasks"][0]["question"] == "che orari fate?"
    assert body["tasks"][0]["count"] == 1


def test_vuoto_senza_segnali():
    out = metrics.learning_tasks()
    assert out["tasks"] == []
