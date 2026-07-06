"""Osservabilità errori con Sentry (opzionale).

Inerte finché `SENTRY_DSN` è vuota; con la DSN cattura le eccezioni non gestite
(integrazione FastAPI/Starlette automatica di sentry-sdk). La libreria è importata
in modo pigro, così Ember gira anche senza. Privacy: `send_default_pii=False`.
"""
import logging

from .config import settings

log = logging.getLogger("ember.obs")


def enabled() -> bool:
    return bool(settings.sentry_dsn.strip())


def init_sentry() -> bool:
    """Inizializza Sentry se configurato. Ritorna True se attivato. Non solleva mai."""
    if not enabled():
        return False
    try:
        import sentry_sdk
        sentry_sdk.init(
            dsn=settings.sentry_dsn.strip(),
            environment=(settings.sentry_env.strip() or "production"),
            traces_sample_rate=0.0,
            send_default_pii=False,
        )
        log.info("Sentry attivo (environment=%s)", settings.sentry_env.strip() or "production")
        return True
    except Exception:  # pragma: no cover - dipendenza/rete
        log.warning("Sentry non inizializzato", exc_info=True)
        return False
