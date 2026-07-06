"""Multilingua: system prompt e 'non lo so' per lingua; /config espone lang."""
from fastapi.testclient import TestClient

from app import rag, main, tenants
from app.config import settings

client = TestClient(main.app)


def test_system_default_it():
    assert "Rispondi in italiano" in rag._system("it")
    assert rag._system() == rag.SYSTEM        # default = italiano (retro-compat)


def test_system_en():
    s = rag._system("en")
    assert "Answer in English" in s and rag._NO_ANSWER_EN in s


def test_lang_normalize():
    assert rag._lang("en-US") == "en" and rag._lang("EN") == "en"
    for x in ("it", "", None, "fr"):
        assert rag._lang(x) == "it"           # tutto ciò che non è 'en' → it


def test_no_answer_lang():
    assert rag.no_answer("en") == rag._NO_ANSWER_EN
    assert rag.no_answer("it") == rag.NO_ANSWER


def test_answer_no_hits_lang(monkeypatch):
    monkeypatch.setattr(rag, "_retrieve", lambda q, g, k: [])
    assert rag.answer("q", ["ats"], lang="en")["answer"] == rag._NO_ANSWER_EN
    assert rag.answer("q", ["ats"])["answer"] == rag.NO_ANSWER   # default it


def test_config_espone_lang(monkeypatch):
    monkeypatch.setattr(tenants, "get_tenant_by_key", lambda k: {"name": "X", "branding": {"lang": "en"}})
    assert client.get("/config", headers={"X-Tenant-Key": "K"}).json()["lang"] == "en"
    monkeypatch.setattr(tenants, "get_tenant_by_key", lambda k: {"name": "Y", "branding": {}})
    assert client.get("/config", headers={"X-Tenant-Key": "K"}).json()["lang"] == settings.default_lang
