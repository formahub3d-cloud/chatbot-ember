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


# Istanza condivisa dal processo. Per Redis: creare un limiter equivalente e
# importarlo qui al posto di questo, oppure iniettarlo in main.py.
limiter = SlidingWindowLimiter()
