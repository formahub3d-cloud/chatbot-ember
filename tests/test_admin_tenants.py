"""Admin tenant API: list/create/revoke/brand (wrapper HTTP di manage_apikeys),
protetti da ADMIN_TOKEN e dal backend Supabase. manage_apikeys mockato."""
from fastapi.testclient import TestClient

from app import main, manage_apikeys as M, tenants
from app.config import settings

client = TestClient(main.app)


def _en(monkeypatch):
    monkeypatch.setattr(settings, "admin_token", "SEG")
    monkeypatch.setattr(tenants, "_apikeys_enabled", lambda: True)


def _h():
    return {"Authorization": "Bearer SEG"}


def test_list(monkeypatch):
    _en(monkeypatch)
    monkeypatch.setattr(M, "list_keys", lambda: [{"name": "X", "active": True}])
    assert client.get("/admin/tenants").status_code == 401          # senza token
    r = client.get("/admin/tenants", headers=_h())
    assert r.status_code == 200 and r.json()["tenants"][0]["name"] == "X"


def test_create(monkeypatch):
    _en(monkeypatch)
    called = {}

    def fake_create(name, orgs, tenants_, subs, origins, quota, branding):
        called.update(name=name, orgs=orgs, tenants=tenants_, quota=quota, branding=branding)
        return "ovy_ABC123"
    monkeypatch.setattr(M, "create_key", fake_create)
    r = client.post("/admin/tenants",
                    json={"name": "Cliente X", "orgs": "forma", "tenants": "x",
                          "quota": 2000, "branding": {"title": "X"}}, headers=_h())
    assert r.status_code == 200 and r.json()["key"] == "ovy_ABC123"
    assert called["name"] == "Cliente X" and called["branding"] == {"title": "X"}


def test_revoke(monkeypatch):
    _en(monkeypatch)
    monkeypatch.setattr(M, "revoke", lambda n: 2)
    r = client.post("/admin/tenants/revoke", json={"name": "X"}, headers=_h())
    assert r.status_code == 200 and r.json()["revoked"] == 2


def test_brand(monkeypatch):
    _en(monkeypatch)
    monkeypatch.setattr(M, "set_branding", lambda n, b: 1)
    r = client.post("/admin/tenants/brand", json={"name": "X", "branding": {"accent": "#000"}}, headers=_h())
    assert r.status_code == 200 and r.json()["updated"] == 1


def test_backend_off(monkeypatch):
    monkeypatch.setattr(settings, "admin_token", "SEG")
    monkeypatch.setattr(tenants, "_apikeys_enabled", lambda: False)
    assert client.get("/admin/tenants", headers=_h()).status_code == 400
