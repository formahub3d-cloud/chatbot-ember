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


def test_macchina_a_stati_azione_con_approvazione():
    # Z2: un'azione con effetto esterno nasce in-approvazione e NON parte senza ok
    a = braintasks.add("Invia 3 solleciti", scope="ats", kind="azione",
                       status="in-approvazione", idempotency_key="sollecito-ats-1")
    assert a["status"] == "in-approvazione"
    dup = braintasks.add("Invia 3 solleciti", kind="azione",
                         status="in-approvazione", idempotency_key="sollecito-ats-1")
    assert dup.get("duplicate") is True                      # idempotenza: mai due volte
    assert not braintasks.transition(a["id"], "in-esecuzione")   # salto vietato
    assert not braintasks.transition(a["id"], "approvata", by="")  # serve chi approva
    assert braintasks.transition(a["id"], "approvata", by="Andrea")
    with braintasks._lock:
        t = next(x for x in braintasks._mem if x["id"] == a["id"])
        assert t["approved_by"] == "Andrea" and t["approved_at"]
    assert braintasks.transition(a["id"], "in-esecuzione")
    assert braintasks.transition(a["id"], "fallita", error="SMTP giù")
    with braintasks._lock:
        assert t["status"] == "fallita" and t["error"] == "SMTP giù"
        assert t["closed_by"] == "sistema"                   # mai DELETE, sempre chiuso
    assert not braintasks.transition(a["id"], "approvata", by="Andrea")  # terminale


def test_rifiuto_archivia_mai_delete():
    a = braintasks.add("Azione da rifiutare", kind="azione", status="in-approvazione")
    assert braintasks.transition(a["id"], "archiviata", by="Andrea")
    assert braintasks.list_open() == []
    with braintasks._lock:
        assert braintasks._mem[0]["status"] == "archiviata"  # archiviata, non cancellata
    assert braintasks.add("x", status="in-esecuzione") is None  # nascita solo aperta/in-approvazione


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
    # macchina a stati via API: crea azione, filtra per stato, approva, esegue
    r2 = client.post("/admin/tasks", headers=_h(),
                     json={"title": "Crea evento Calendar", "kind": "azione",
                           "status": "in-approvazione"})
    aid = r2.json()["task"]["id"]
    wait = client.get("/admin/tasks?status=in-approvazione", headers=_h()).json()["tasks"]
    assert [t["id"] for t in wait] == [aid]
    assert client.post("/admin/tasks/transition", headers=_h(),
                       json={"id": aid, "to": "approvata"}).status_code == 422   # senza by
    assert client.post("/admin/tasks/transition", headers=_h(),
                       json={"id": aid, "to": "approvata", "by": "Andrea"}).status_code == 200
    assert client.post("/admin/tasks/transition", headers=_h(),
                       json={"id": aid, "to": "in-esecuzione"}).status_code == 200
    assert client.post("/admin/tasks/transition", headers=_h(),
                       json={"id": aid, "to": "fatta", "by": "Dante"}).status_code == 200
    assert client.post("/admin/tasks/transition",
                       json={"id": aid, "to": "fatta", "by": "x"}).status_code == 401
