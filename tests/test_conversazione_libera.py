"""O4 · Conversazione libera — SOLO OWNER, provenienza visibile, ingresso marcato.

Regole tassative del task, ognuna con un test:
1. SOLO OWNER: il permesso è un flag server-side sul record del tenant, non un
   interruttore d'interfaccia né un parametro della richiesta.
2. LA PROVENIENZA SI VEDE: il prompt impone i marcatori ⟦fuori⟧…⟦/fuori⟧ su
   tutto ciò che non nasce dal CONTENUTO.
3. QUELLO CHE ENTRA, ENTRA MARCATO: /writeback con origin=conversazione
   antepone «Origine: conversazione con Divina · data · NON verificato» — e lo
   fa il SERVER, non il client.
4. NIENTE SALVATAGGI AUTOMATICI: senza confirm=true resta un'anteprima.
"""
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app import main, rag, tenants, security, writeback

client = TestClient(main.app)


def _hit():
    return SimpleNamespace(score=0.9, payload={"slug": "nota-x", "text": "contenuto utile"})


# ── 1 · SOLO OWNER, deciso server-side ───────────────────────────────────────
def test_is_owner_solo_da_flag_del_record():
    assert main._is_owner({"owner": True}) is True
    assert main._is_owner({"branding": {"owner": True}}) is True
    assert main._is_owner({}) is False
    assert main._is_owner({"owner": "true"}) is False          # solo True booleano
    assert main._is_owner({"branding": {"owner": 1}}) is False


def test_chat_owner_attiva_free_il_cliente_mai(monkeypatch):
    seen = {}
    monkeypatch.setattr(security, "origin_allowed", lambda o, a: True)
    monkeypatch.setattr(main, "rate_ok", lambda k: True)
    monkeypatch.setattr(rag, "answer", lambda q, g, **kw: (seen.update(kw), {"answer": "ok", "sources": [], "scopes": []})[1])

    monkeypatch.setattr(tenants, "get_tenant_by_key",
                        lambda k: {"name": "FORMA", "allowed_origins": [], "allowed_scopes": ["forma-core"], "owner": True})
    client.post("/chat", json={"message": "ciao"}, headers={"X-Tenant-Key": "K"})
    assert seen["free"] is True

    monkeypatch.setattr(tenants, "get_tenant_by_key",
                        lambda k: {"name": "ATS", "allowed_origins": [], "allowed_scopes": ["ats"]})
    client.post("/chat", json={"message": "ciao"}, headers={"X-Tenant-Key": "K"})
    assert seen["free"] is False


def test_il_client_non_puo_chiedere_free_dal_payload(monkeypatch):
    """Il flag non esiste in ChatIn: qualunque campo extra nel body è ignorato."""
    seen = {}
    monkeypatch.setattr(security, "origin_allowed", lambda o, a: True)
    monkeypatch.setattr(main, "rate_ok", lambda k: True)
    monkeypatch.setattr(tenants, "get_tenant_by_key",
                        lambda k: {"name": "ATS", "allowed_origins": [], "allowed_scopes": ["ats"]})
    monkeypatch.setattr(rag, "answer", lambda q, g, **kw: (seen.update(kw), {"answer": "ok", "sources": [], "scopes": []})[1])
    client.post("/chat", json={"message": "ciao", "free": True, "owner": True},
                headers={"X-Tenant-Key": "K"})
    assert seen["free"] is False


# ── 2 · La provenienza si vede: marcatori imposti dal prompt ─────────────────
def test_prompt_free_impone_i_marcatori_di_provenienza():
    s = rag._system("it", free=True)
    assert "⟦fuori⟧" in s and "⟦/fuori⟧" in s
    assert "TITOLARE" in s
    # senza free il prompt resta ESATTAMENTE quello di sempre
    assert rag._system("it") == rag.SYSTEM
    assert "⟦fuori⟧" not in rag._system("it")


def test_answer_free_supera_il_muro_ma_traccia_il_gap(monkeypatch):
    """Owner + zero hit: niente «non ho questa informazione» — si ragiona,
    col gap comunque tracciato e la risposta marcata free."""
    seen = {}
    monkeypatch.setattr(rag, "_retrieve", lambda q, g, k, focus_slugs=None: [])
    monkeypatch.setattr(rag, "chat", lambda s, u: (seen.update(sys=s), "⟦fuori⟧ragioniamo⟦/fuori⟧")[1])
    out = rag.answer("domanda nuova", {"allowed_scopes": ["forma-core"]}, free=True)
    assert out["answer"] != rag.NO_ANSWER
    assert out.get("free") is True
    assert "⟦fuori⟧" in seen["sys"]
    # il tenant normale, stessa situazione: muro come sempre
    out2 = rag.answer("domanda nuova", {"allowed_scopes": ["ats"]})
    assert out2["answer"] == rag.NO_ANSWER and "free" not in out2


# ── 3+4 · Quello che entra, entra marcato — e mai in automatico ──────────────
def _wb_setup(monkeypatch, seen):
    monkeypatch.setattr(security, "origin_allowed", lambda o, a: True)
    monkeypatch.setattr(main, "rate_ok", lambda k: True)
    monkeypatch.setattr(tenants, "get_tenant_by_key",
                        lambda k: {"name": "FORMA", "allowed_origins": [], "allowed_scopes": ["forma-core"], "owner": True})
    monkeypatch.setattr(main, "_billing_ok", lambda t: True, raising=False)
    monkeypatch.setattr(writeback, "render_note",
                        lambda scope, title, body, summary, tags: f"[{scope}] {title}\n{body}")
    monkeypatch.setattr(writeback, "save_note",
                        lambda scope, title, body, summary, tags, overwrite=False:
                        (seen.update(body=body), {"created": True, "path": "forma/x.md"})[1])
    monkeypatch.setattr(tenants, "log_access", lambda *a, **k: None)


def test_writeback_da_conversazione_entra_marcato_dal_server(monkeypatch):
    seen = {}
    _wb_setup(monkeypatch, seen)
    r = client.post("/writeback", json={"scope": "forma-core", "title": "Idea di business",
                                        "body": "contenuto ragionato insieme",
                                        "origin": "conversazione", "confirm": True},
                    headers={"X-Tenant-Key": "K"})
    assert r.status_code == 200
    assert seen["body"].startswith("> Origine: conversazione con Divina · ")
    assert "NON verificato" in seen["body"].splitlines()[0]
    assert "contenuto ragionato insieme" in seen["body"]


def test_writeback_normale_non_viene_marcato(monkeypatch):
    seen = {}
    _wb_setup(monkeypatch, seen)
    client.post("/writeback", json={"scope": "forma-core", "title": "Nota", "body": "testo",
                                    "confirm": True},
                headers={"X-Tenant-Key": "K"})
    assert "Origine: conversazione" not in seen["body"]


def test_writeback_senza_confirm_resta_anteprima(monkeypatch):
    seen = {}
    _wb_setup(monkeypatch, seen)
    r = client.post("/writeback", json={"scope": "forma-core", "title": "Nota", "body": "testo",
                                        "origin": "conversazione"},
                    headers={"X-Tenant-Key": "K"})
    assert r.status_code == 200
    assert r.json()["consolidato"] is False
    assert "NON verificato" in r.json()["preview"]      # l'anteprima mostra la marcatura
    assert "body" not in seen                           # e NIENTE è stato scritto
