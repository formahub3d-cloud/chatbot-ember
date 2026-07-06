"""Sentry opzionale: off senza DSN, init con sentry_sdk FINTO (nessuna rete)."""
import sys
import types

from app import obs
from app.config import settings


def test_disabled_default(monkeypatch):
    monkeypatch.setattr(settings, "sentry_dsn", "")
    assert obs.enabled() is False
    assert obs.init_sentry() is False


def test_init_con_sentry_finto(monkeypatch):
    monkeypatch.setattr(settings, "sentry_dsn", "https://k@o.ingest.sentry.io/1")
    monkeypatch.setattr(settings, "sentry_env", "test")
    captured = {}
    fake = types.ModuleType("sentry_sdk")
    fake.init = lambda **kw: captured.update(kw)
    monkeypatch.setitem(sys.modules, "sentry_sdk", fake)
    assert obs.init_sentry() is True
    assert captured["dsn"].endswith("/1") and captured["environment"] == "test"
    assert captured["send_default_pii"] is False and captured["traces_sample_rate"] == 0.0
