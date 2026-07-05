"""Test del rate limiting (backend in memoria + fallback Redis). Puro, senza rete."""
from app import ratelimit
from app.config import settings


def setup_function():
    ratelimit.reset()


def test_illimitato_con_limite_zero():
    assert ratelimit.allow("t", 0) is True
    assert ratelimit.allow("t", -5) is True


def test_memoria_blocca_oltre_il_limite():
    assert ratelimit.allow("tenant-a", 2) is True
    assert ratelimit.allow("tenant-a", 2) is True
    assert ratelimit.allow("tenant-a", 2) is False   # terzo colpo nella finestra


def test_chiavi_indipendenti():
    assert ratelimit.allow("a", 1) is True
    assert ratelimit.allow("b", 1) is True           # chiave diversa, contatore proprio
    assert ratelimit.allow("a", 1) is False


def test_fallback_a_memoria_se_redis_non_raggiungibile(monkeypatch):
    """Con REDIS_URL impostata ma Redis irraggiungibile, si degrada alla memoria
    senza sollevare: il servizio continua a limitare (per-istanza)."""
    monkeypatch.setattr(settings, "redis_url", "redis://127.0.0.1:1/0")
    ratelimit.reset()
    # _get_redis prova a connettersi, fallisce (porta chiusa) e ritorna None.
    assert ratelimit._get_redis() is None
    assert ratelimit.allow("x", 1) is True
    assert ratelimit.allow("x", 1) is False


def test_backend_redis_usato_quando_disponibile(monkeypatch):
    """Se un client Redis è disponibile, allow() usa INCR sul bucket condiviso."""
    store = {}

    class FakeRedis:
        def incr(self, k):
            store[k] = store.get(k, 0) + 1
            return store[k]

        def expire(self, k, w):
            pass

    monkeypatch.setattr(settings, "redis_url", "redis://fake")
    ratelimit.reset()
    monkeypatch.setattr(ratelimit, "_get_redis", lambda: FakeRedis())

    assert ratelimit.allow("y", 2) is True
    assert ratelimit.allow("y", 2) is True
    assert ratelimit.allow("y", 2) is False
