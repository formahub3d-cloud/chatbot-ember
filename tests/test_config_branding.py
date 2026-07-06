"""White-label: /config restituisce il branding del tenant (dalla chiave) e i
default quando i campi non sono valorizzati."""
from fastapi.testclient import TestClient

from app import main, tenants
from app.config import settings

client = TestClient(main.app)


def test_config_branding_completo(monkeypatch):
    t = {"name": "ATS Bot", "allowed_scopes": ["ats"], "branding": {
        "title": "Assistente ATS", "subtitle": "Recruiting AI", "accent": "#DD24F2",
        "avatar": "https://cdn/ats.png", "logo": "https://cdn/ats-logo.png",
        "greeting": "Ciao, sono l'assistente ATS!"}}
    monkeypatch.setattr(tenants, "get_tenant_by_key", lambda k: t)
    b = client.get("/config", headers={"X-Tenant-Key": "K"}).json()
    assert b["title"] == "Assistente ATS"
    assert b["subtitle"] == "Recruiting AI"
    assert b["accent"] == "#DD24F2"
    assert b["avatar"] == "https://cdn/ats.png"
    assert b["logo"] == "https://cdn/ats-logo.png"
    assert b["greeting"] == "Ciao, sono l'assistente ATS!"


def test_config_default_senza_branding(monkeypatch):
    monkeypatch.setattr(tenants, "get_tenant_by_key", lambda k: {"name": "X", "branding": {}})
    b = client.get("/config", headers={"X-Tenant-Key": "K"}).json()
    assert b["title"] == "X" and b["accent"] == "#0ED4E4"
    assert "avatar" not in b and "logo" not in b and "greeting" not in b   # inviati solo se valorizzati


def test_config_chiave_non_valida(monkeypatch):
    monkeypatch.setattr(tenants, "get_tenant_by_key", lambda k: None)
    assert client.get("/config", headers={"X-Tenant-Key": "X"}).status_code == 401
