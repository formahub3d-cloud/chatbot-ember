"""Coda task persistente del cervello (/admin/tasks): fallback in-memory nei test
(Supabase off), creazione, chiusura solo umana ('fatta'/'archiviata'), mai DELETE."""
from fastapi.testclient import TestClient

from app import braintasks, main
from app.config import settings

client = TestClient(main.app)


def setup_function(_):
    braintasks.reset()


def _h():
    return {"Authorization": "Bearer SEG"}


def test_add_e_list_open():
    assert braintasks.add("") is None                      # titolo obbligatorio
    t = braintasks.add("Arricchisci nota resi", scope="ats", kind="gap")
    assert t["status"] == "aperta" and t["kind"] == "gap" and t["id"]
    t2 = braintasks.add("Task generica", kind="sconosciuto")
    assert t2["kind"] == "manuale"                          # kind fuori catalogo → manuale
    aperte = braintasks.list_open()
    assert [x["title"] for x in aperte] == ["Task generica", "Arricchisci nota resi"]


def test_close_solo_umano_mai_delete():
    t = braintasks.add("Da chiudere")
    assert not braintasks.close(t["id"], "", "fatta")       # serve il nome di chi decide
    assert not braintasks.close(t["id"], "Andrea", "eliminata")  # status fuori catalogo
    assert braintasks.close(t["id"], "Andrea", "fatta")
    assert not braintasks.close(t["id"], "Andrea", "fatta")  # già chiusa
    assert braintasks.list_open() == []
    with braintasks._lock:                                   # archiviata, non cancellata
        assert braintasks._mem[0]["status"] == "fatta"
        assert braintasks._mem[0]["closed_by"] == "Andrea"


def test_endpoints(monkeypatch):
    monkeypatch.setattr(settings, "admin_token", "SEG")
    assert client.get("/admin/tasks").status_code == 401
    r = client.post("/admin/tasks", headers=_h(),
                    json={"title": "Nota orari weekend", "scope": "ats"})
    assert r.status_code == 200 and r.json()["task"]["scope"] == "ats"
    tid = r.json()["task"]["id"]
    body = client.get("/admin/tasks", headers=_h()).json()
    assert body["persist"] is False                          # nei test Supabase è off
    assert body["tasks"][0]["id"] == tid
    assert client.post("/admin/tasks", headers=_h(), json={"title": "  "}).status_code == 422
    assert client.post("/admin/tasks/close", headers=_h(),
                       json={"id": tid, "by": ""}).status_code == 422
    assert client.post("/admin/tasks/close", headers=_h(),
                       json={"id": tid, "by": "Andrea", "status": "eliminata"}).status_code == 422
    assert client.post("/admin/tasks/close", headers=_h(),
                       json={"id": tid, "by": "Andrea"}).status_code == 200
    assert client.post("/admin/tasks/close", headers=_h(),
                       json={"id": tid, "by": "Andrea"}).status_code == 404
