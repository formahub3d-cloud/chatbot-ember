"""Accessi console cliente gestiti da FORMA (app/clientauth.py + /client/*).

Modello: FORMA provisiona account + chiave tenant server-side; primo accesso
email+password, poi SOLO codice a 6 cifre generato da FORMA; sessioni HMAC in
cookie HttpOnly; fail-closed senza CLIENT_SESSION_SECRET; lockout a 5 tentativi;
mai DELETE (status='rimosso'); la chiave master non è mai assegnabile."""
import pytest
from fastapi.testclient import TestClient

from app import clientauth, main, rag, security, tenants
from app.config import settings

client = TestClient(main.app)


@pytest.fixture(autouse=True)
def _pulizia(monkeypatch):
    """Store in memoria pulito, feature accesa, admin forte, DB spento."""
    clientauth._MEM.clear()
    monkeypatch.setattr(settings, "client_session_secret", "s" * 32)
    monkeypatch.setattr(settings, "admin_token", "T" * 32)
    monkeypatch.setattr(settings, "database_url", "")
    yield
    clientauth._MEM.clear()


def _adm():
    return {"Authorization": "Bearer " + "T" * 32}


def _tenant_ok(monkeypatch, scopes=("ats",)):
    t = {"name": "Cliente", "allowed_scopes": list(scopes),
         "allowed_origins": [], "branding": {}}
    monkeypatch.setattr(tenants, "get_tenant_by_key", lambda k: t)
    return t


def _crea(monkeypatch, email="anna@ats.it", pw="password-lunga"):
    _tenant_ok(monkeypatch)
    return clientauth.create(email, "Anna", "K-ATS", pw)


# ── fail-closed: senza segreto la feature NON esiste ──────────────────────────
def test_fail_closed_senza_segreto(monkeypatch):
    monkeypatch.setattr(settings, "client_session_secret", "")
    assert clientauth.enabled() is False
    r = client.post("/client/login", json={"email": "a@b.it", "credential": "x"})
    assert r.status_code == 503
    assert client.get("/admin/clients", headers=_adm()).status_code == 503
    # anche una sessione "valida" firmata prima non apre nulla
    assert clientauth.check_session("qualunque.cosa") is None


# ── creazione (solo FORMA): validazioni e chiave mai al client ────────────────
def test_create_validazioni(monkeypatch):
    _tenant_ok(monkeypatch)
    with pytest.raises(ValueError):
        clientauth.create("non-email", "X", "K", "password-lunga")
    with pytest.raises(ValueError):
        clientauth.create("a@b.it", "X", "", "password-lunga")
    with pytest.raises(ValueError):
        clientauth.create("a@b.it", "X", "K", "corta")           # pw < 8
    monkeypatch.setattr(tenants, "get_tenant_by_key", lambda k: None)
    with pytest.raises(ValueError):
        clientauth.create("a@b.it", "X", "K-IGNOTA", "password-lunga")


def test_create_rifiuta_master_e_duplicati(monkeypatch):
    _tenant_ok(monkeypatch, scopes=("*",))
    with pytest.raises(ValueError):                              # mai la master
        clientauth.create("a@b.it", "X", "K-MASTER", "password-lunga")
    acc = _crea(monkeypatch)
    assert acc["email"] == "anna@ats.it" and acc["pin_set"] is False
    with pytest.raises(ValueError):                              # email doppia
        _crea(monkeypatch)


def test_lista_senza_segreti(monkeypatch):
    _crea(monkeypatch)
    r = client.get("/admin/clients", headers=_adm())
    assert r.status_code == 200
    row = r.json()["clients"][0]
    testo = str(row).lower()
    assert "hash" not in testo and "tenant_key" not in testo and "k-ats" not in testo


# ── login: password al primo accesso, poi SOLO il codice a 6 cifre ────────────
def test_login_password_poi_pin(monkeypatch):
    acc = _crea(monkeypatch)
    assert clientauth.login("anna@ats.it", "password-lunga")["id"] == acc["id"]
    code = clientauth.set_pin(acc["id"])
    assert len(code) == 6 and code.isdigit()
    # col PIN generato la password è SPENTA, si entra solo col codice
    assert clientauth.login("anna@ats.it", "password-lunga") is None
    assert clientauth.login("anna@ats.it", code)["id"] == acc["id"]


def test_lockout_e_sblocco_via_rigenera(monkeypatch):
    acc = _crea(monkeypatch)
    for _ in range(clientauth.MAX_ATTEMPTS):
        assert clientauth.login("anna@ats.it", "sbagliata") is None
    # bloccato: nemmeno la credenziale giusta apre
    assert clientauth.login("anna@ats.it", "password-lunga") is None
    # SOLO FORMA sblocca, rigenerando il codice
    code = clientauth.set_pin(acc["id"])
    assert clientauth.login("anna@ats.it", code)["id"] == acc["id"]


def test_sospensione_taglia_anche_le_sessioni(monkeypatch):
    acc = _crea(monkeypatch)
    tok = clientauth.make_session(acc["id"])
    assert clientauth.check_session(tok)["account"]["id"] == acc["id"]
    clientauth.set_status(acc["id"], "sospeso")
    assert clientauth.login("anna@ats.it", "password-lunga") is None
    assert clientauth.check_session(tok) is None      # sessione già emessa: fuori
    clientauth.set_status(acc["id"], "attivo")
    assert clientauth.check_session(tok) is not None


def test_sessione_manomessa_o_scaduta(monkeypatch):
    acc = _crea(monkeypatch)
    tok = clientauth.make_session(acc["id"])
    assert clientauth.check_session(tok + "x") is None            # firma rotta
    raw, sig = tok.rsplit(".", 1)
    assert clientauth.check_session(raw + ".deadbeef") is None
    monkeypatch.setitem(clientauth.SESSION_TTL, "client", -10)    # già scaduta
    assert clientauth.check_session(clientauth.make_session(acc["id"])) is None


def test_rimozione_e_archivio_non_delete(monkeypatch):
    acc = _crea(monkeypatch)
    clientauth.set_status(acc["id"], "rimosso")
    assert clientauth.list_accounts() == []                       # sparisce dalla lista
    assert clientauth._MEM                                        # ma il record RESTA


# ── endpoint end-to-end: login → me → chat con chiave SERVER-SIDE ─────────────
def test_endpoint_login_me_chat(monkeypatch):
    acc = _crea(monkeypatch)
    monkeypatch.setattr(security, "origin_allowed", lambda o, a: True)
    monkeypatch.setattr(main, "rate_ok", lambda k: True)
    monkeypatch.setattr(tenants, "quota_ok", lambda t: True)
    visto = {}

    from types import SimpleNamespace

    def fake_retrieve(q, g, k):
        visto["grants"] = g
        return [SimpleNamespace(score=0.9, payload={"slug": "nota", "scope": "ats",
                                                    "title": "Nota", "text": "contenuto"})]
    monkeypatch.setattr(rag, "_retrieve", fake_retrieve)
    monkeypatch.setattr(rag, "chat", lambda s, u: "risposta-cervello")

    r = client.post("/client/login", json={"email": "anna@ats.it",
                                           "credential": "password-lunga"})
    assert r.status_code == 200 and r.json()["ok"] is True
    assert "dv_client" in r.cookies                                # cookie di sessione
    r2 = client.get("/client/me")
    assert r2.status_code == 200
    assert r2.json()["account"]["email"] == "anna@ats.it"
    assert r2.json()["kind"] == "client"
    # chat SENZA X-Tenant-Key: la chiave la mette il server
    r3 = client.post("/client/chat", json={"message": "ciao"})
    assert r3.status_code == 200
    assert r3.json()["answer"] == "risposta-cervello"
    assert visto["grants"]["allowed_scopes"] == ["ats"]            # scope del tenant


def test_endpoint_login_sbagliato_401_uniforme(monkeypatch):
    _crea(monkeypatch)
    monkeypatch.setattr(main, "rate_ok", lambda k: True)
    # email inesistente ed errata: STESSA risposta (niente oracoli)
    a = client.post("/client/login", json={"email": "ignota@x.it", "credential": "x"})
    b = client.post("/client/login", json={"email": "anna@ats.it", "credential": "x"})
    assert a.status_code == b.status_code == 401
    assert a.json() == b.json()


def test_endpoint_chat_senza_sessione_401():
    client.cookies.clear()
    assert client.post("/client/chat", json={"message": "ciao"}).status_code == 401
    assert client.get("/client/me").status_code == 401


def test_admin_endpoints_protetti(monkeypatch):
    acc = _crea(monkeypatch)
    assert client.get("/admin/clients").status_code == 401
    assert client.post("/admin/clients/pin", json={"id": acc["id"]}).status_code == 401
    r = client.post("/admin/clients/pin", json={"id": acc["id"]}, headers=_adm())
    assert r.status_code == 200 and len(r.json()["code"]) == 6
    assert client.post("/admin/clients/pin", json={"id": "manca"},
                       headers=_adm()).status_code == 404


def test_admin_ghost_apre_sessione_cliente(monkeypatch):
    acc = _crea(monkeypatch)
    client.cookies.clear()
    r = client.post("/admin/clients/ghost", json={"id": acc["id"]}, headers=_adm())
    assert r.status_code == 200
    r2 = client.get("/client/me")
    assert r2.status_code == 200 and r2.json()["kind"] == "ghost"  # banner in console
    client.cookies.clear()
