"""Rate limiting per chiave tenant — finestra scorrevole di 60s, in memoria.

Estratto dagli endpoint dietro una piccola interfaccia (`allow`) così che, per il
multi-istanza (più repliche sullo stesso servizio), si possa sostituire con un
backend Redis senza toccare main.py: basta esporre un oggetto con lo stesso
metodo `allow(key, limit)`. Thread-safe. In-memory = si azzera al redeploy e non
è condiviso tra repliche (limite noto, vedi roadmap DevOps).
"""
import time
from collections import deque
from threading import Lock


class SlidingWindowLimiter:
    """Consente al più `limit` richieste per `key` in una finestra di `window_s`."""

    def __init__(self, window_s: float = 60.0):
        self.window_s = window_s
        self._hits: dict = {}
        self._lock = Lock()

    def allow(self, key: str, limit: int, now: float | None = None) -> bool:
        """True se la richiesta è ammessa (e la registra); False se supera il limite.
        `limit <= 0` = nessun limite. `now` iniettabile per i test."""
        if limit <= 0:
            return True
        t = time.time() if now is None else now
        with self._lock:
            dq = self._hits.setdefault(key, deque())
            while dq and t - dq[0] > self.window_s:
                dq.popleft()
            if len(dq) >= limit:
                return False
            dq.append(t)
            return True

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


class RedisLimiter:
    """Rate limit condiviso tra repliche via Redis (finestra scorrevole su sorted-set).

    Per ogni chiave tiene un sorted-set di timestamp: si eliminano quelli fuori
    finestra, si conta, e se sotto soglia si aggiunge il nuovo. Stessa firma di
    SlidingWindowLimiter, così è intercambiabile. `client` iniettabile per i test.
    Nota: check-then-add non è atomico (accettabile per un rate-limit); per garanzie
    forti si userebbe uno script Lua."""

    def __init__(self, url: str | None = None, window_s: float = 60.0,
                 client=None, prefix: str = "ratelimit:"):
        self.window_s = window_s
        self.prefix = prefix
        if client is not None:
            self.client = client
        else:  # pragma: no cover - richiede la libreria redis e un server
            import redis  # import pigro: serve solo se REDIS_URL è impostata
            self.client = redis.Redis.from_url(url, decode_responses=True)

    def allow(self, key: str, limit: int, now: float | None = None) -> bool:
        if limit <= 0:
            return True
        import uuid
        t = time.time() if now is None else now
        rk = self.prefix + key
        c = self.client
        c.zremrangebyscore(rk, 0, t - self.window_s)
        if c.zcard(rk) >= limit:
            return False
        c.zadd(rk, {f"{t}:{uuid.uuid4().hex}": t})
        c.expire(rk, int(self.window_s) + 1)
        return True


def make_limiter():
    """Sceglie il limiter dalla configurazione: Redis se REDIS_URL è valorizzata
    (con fallback in-memory se la libreria manca o la connessione fallisce),
    altrimenti in-memory. Chiamata all'import di main.py."""
    from .config import settings
    url = (settings.redis_url or "").strip()
    if not url:
        return SlidingWindowLimiter()
    try:  # pragma: no cover - percorso con dipendenza esterna
        import logging
        rl = RedisLimiter(url=url)
        rl.client.ping()
        logging.getLogger("ember.ratelimit").info("rate-limit: backend Redis attivo")
        return rl
    except Exception:  # pragma: no cover
        import logging
        logging.getLogger("ember.ratelimit").warning(
            "REDIS_URL impostata ma Redis non raggiungibile/assente: uso il limiter in-memory")
        return SlidingWindowLimiter()


# Istanza condivisa dal processo, scelta dalla configurazione.
limiter = make_limiter()
