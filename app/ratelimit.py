"""Rate limiting per chiave tenant, con due backend.

- **In memoria** (default): finestra scorrevole di 60s nel processo. Semplice e
  senza dipendenze, ma il limite è PER-ISTANZA: con più repliche è aggirabile.
- **Redis** (opzionale, `REDIS_URL`): contatore a finestra fissa CONDIVISO tra le
  istanze (INCR + EXPIRE atomici). È il backend da usare in produzione multi-replica.

Se Redis è configurato ma non raggiungibile, si degrada al backend in memoria
(fail-safe: il servizio continua a funzionare, il limite torna per-istanza).
"""
import logging
import time
from collections import deque

from .config import settings

log = logging.getLogger("ember.ratelimit")

# Stato in memoria: coda di timestamp per chiave (finestra scorrevole).
_hits: dict[str, deque] = {}

# Client Redis risolto pigramente una sola volta (None = usa la memoria).
_redis = None
_redis_resolved = False


def _mem_allow(key: str, limit: int, window: int = 60) -> bool:
    now = time.time()
    dq = _hits.setdefault(key, deque())
    while dq and now - dq[0] > window:
        dq.popleft()
    if len(dq) >= limit:
        return False
    dq.append(now)
    return True


def _get_redis():
    """Risolve il client Redis una volta sola. None se non configurato o non
    raggiungibile (in tal caso si usa il backend in memoria)."""
    global _redis, _redis_resolved
    if _redis_resolved:
        return _redis
    _redis_resolved = True
    url = settings.redis_url.strip()
    if url:
        try:
            import redis  # import locale: dipendenza necessaria solo con REDIS_URL
            client = redis.Redis.from_url(url, socket_timeout=2, socket_connect_timeout=2)
            client.ping()
            _redis = client
            log.info("Rate-limit: backend Redis attivo (condiviso tra le istanze).")
        except Exception:
            log.exception("Redis non raggiungibile: rate-limit in memoria (per-istanza).")
            _redis = None
    return _redis


def _redis_allow(client, key: str, limit: int, window: int = 60) -> bool:
    """Finestra FISSA su Redis: INCR della chiave del bucket corrente + EXPIRE.
    Meno preciso dello sliding window ma atomico e condiviso tra le repliche."""
    bucket = int(time.time() // window)
    rkey = f"ratelimit:{key}:{bucket}"
    try:
        n = client.incr(rkey)
        if n == 1:
            client.expire(rkey, window)
        return n <= limit
    except Exception:
        log.exception("Redis rate-limit fallito: fallback in memoria.")
        return _mem_allow(key, limit, window)


def allow(key: str, limit: int, window: int = 60) -> bool:
    """True se la richiesta è sotto il limite. `limit<=0` = illimitato."""
    if limit <= 0:
        return True
    client = _get_redis()
    if client is not None:
        return _redis_allow(client, key, limit, window)
    return _mem_allow(key, limit, window)


def reset() -> None:
    """Azzera lo stato (usato dai test)."""
    global _redis, _redis_resolved
    _hits.clear()
    _redis = None
    _redis_resolved = False
