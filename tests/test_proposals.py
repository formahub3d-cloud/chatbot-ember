"""Proposte di auto-miglioramento (audit → owner, /admin/proposals): generazione
dai segnali, blocklist approva/ignora, approvazione → coda brain_tasks, privacy
(solo ADMIN_TOKEN — mai chiave tenant)."""
from fastapi.testclient import TestClient

from app import braintasks, main, metrics, proposals
from app.config import settings

client = TestClient(main.app)


def setup_function(_):
    metrics.reset()
    braintasks.reset()
    proposals.reset()


def _h():
    return {"Authorization": "Bearer SEG"}


def test_generazione_da_gap_feedback_e_sistema():
    metrics.bump_gap(["ats"], "orari weekend?")
    metrics.bump_feedback(["forma-core"], up=False, question="risposta poco chiara")
    ps = proposals.generate()
    sources = {p["source"] for p in ps}
    assert {"gap", "feedback", "sistema"} <= sources     # nei test le persistenze sono off
    gap = next(p for p in ps if p["source"] == "gap")
    assert "orari weekend?" in gap["title"] and gap["scope"] == "ats"
    assert all(p["id"] for p in ps)
    # id stabile: stessa proposta → stesso id al refresh
    assert gap["id"] == next(p for p in proposals.generate() if p["source"] == "gap")["id"]


def test_approve_crea_task_e_toglie_la_proposta():
    metrics.bump_gap(["ats"], "orari weekend?")
    pid = next(p for p in proposals.generate() if p["source"] == "gap")["id"]
    t = proposals.approve(pid)
    assert t["kind"] == "gap" and t["scope"] == "ats" and t["status"] == "aperta"
    assert braintasks.list_open()[0]["id"] == t["id"]     # è entrata nella coda
    assert pid not in {p["id"] for p in proposals.generate()}
    assert proposals.approve(pid) is None                 # non riappare / non si duplica
    assert proposals.approve("id-inesistente") is None


def test_dismiss_nasconde():
    metrics.bump_gap(["ats"], "orari weekend?")
    pid = next(p for p in proposals.generate() if p["source"] == "gap")["id"]
    proposals.dismiss(pid)
    assert pid not in {p["id"] for p in proposals.generate()}
    assert braintasks.list_open() == []                   # ignorare NON crea task


def test_endpoints_solo_owner(monkeypatch):
    monkeypatch.setattr(settings, "admin_token", "SEG")
    metrics.bump_gap(["ats"], "orari weekend?")
    # privacy: senza ADMIN_TOKEN niente (né con una chiave tenant, che qui non esiste)
    assert client.get("/admin/proposals").status_code == 401
    assert client.post("/admin/proposals/approve", json={"id": "x"}).status_code == 401
    ps = client.get("/admin/proposals", headers=_h()).json()["proposals"]
    pid = next(p for p in ps if p["source"] == "gap")["id"]
    r = client.post("/admin/proposals/approve", headers=_h(), json={"id": pid})
    assert r.status_code == 200 and r.json()["task"]["kind"] == "gap"
    assert client.post("/admin/proposals/approve", headers=_h(),
                       json={"id": pid}).status_code == 404
    assert client.post("/admin/proposals/dismiss", headers=_h(),
                       json={"id": "qualunque"}).status_code == 200