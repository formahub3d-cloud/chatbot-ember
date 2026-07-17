"""Fix sicurezza (collaudo 17-07): gli /admin/* sono FAIL-CLOSED — token
assente o debole/placeholder → 503; token errato → 401; confronto timing-safe.
Il vecchio default 'change-me' rendeva gli admin di fatto pubblici."""
from fastapi.testclient import TestClient

from app import main
from app.config import settings

client = TestClient(main.app)

STRONG = "t0ken-lungo-e-casuale-di-collaudo-123456"


def test_token_debole_o_assente_chiude_503(monkeypatch):
    for weak in ("", "change-me", "password", "ADMIN", "Secret"):
        monkeypatch.setattr(settings, "admin_token", weak)
        r = client.get("/admin/tasks",
                       headers={"Authorization": f"Bearer {weak}"})
        assert r.status_code == 503, f"token debole {weak!r} NON deve mai aprire"
        # anche /ingest usa la stessa guardia
        assert client.post("/ingest",
                           headers={"Authorization": f"Bearer {weak}"}).status_code == 503


def test_token_errato_401_corretto_200(monkeypatch):
    monkeypatch.setattr(settings, "admin_token", STRONG)
    assert client.get("/admin/tasks").status_code == 401
    assert client.get("/admin/tasks",
                      headers={"Authorization": "Bearer password"}).status_code == 401
    assert client.get("/admin/tasks",
                      headers={"Authorization": f"Bearer {STRONG}x"}).status_code == 401
    r = client.get("/admin/tasks", headers={"Authorization": f"Bearer {STRONG}"})
    assert r.status_code == 200


def test_config_senza_default_debole():
    import inspect
    from app import config
    assert 'admin_token: str = "change-me"' not in inspect.getsource(config)
