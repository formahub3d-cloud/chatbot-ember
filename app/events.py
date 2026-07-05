"""Persistenza storica degli eventi conversazione su Supabase (tabella
`analytics_events`), complementare ai contatori in memoria di `metrics`.

I contatori in memoria danno il colpo d'occhio (si azzerano al redeploy); questa
tabella dà lo STORICO (domande frequenti, gap nel tempo, trend feedback). Attiva
solo se ANALYTICS_PERSIST=true e il backend Supabase è configurato. Tutte le
operazioni sono BEST-EFFORT: non devono MAI far fallire una richiesta.

La `question` va passata GIÀ REDATTA (PII rimosse) dal chiamante: qui non si
applica ulteriore redazione, ci si limita a troncare.
"""
import logging

from . import tenants
from .config import settings

log = logging.getLogger("ember.events")

VALID_KINDS = {"chat", "gap", "feedback_up", "feedback_down"}


def enabled() -> bool:
    return (
        settings.analytics_persist
        and settings.grants_backend.strip().lower() == "supabase"
        and bool(settings.database_url.strip())
    )


def _skey(scopes) -> str:
    if not scopes:
        return "∅"
    try:
        return ",".join(sorted(str(s) for s in scopes))
    except Exception:
        return str(scopes)


def record(kind: str, scopes, question: str = "") -> bool:
    """Inserisce un evento. best-effort: ritorna False (senza sollevare) se disattivo
    o in caso di errore. `question` deve essere già redatta."""
    if not enabled() or kind not in VALID_KINDS:
        return False
    q = (question or "").strip()[:400] or None
    try:
        with tenants._conn() as c:
            with c.cursor() as cur:
                cur.execute(
                    "INSERT INTO analytics_events (kind, scope, question) VALUES (%s,%s,%s)",
                    (kind, _skey(scopes), q),
                )
            c.commit()
        return True
    except Exception:  # pragma: no cover - persistenza best-effort, mai bloccante
        log.warning("persistenza evento analytics fallita (ignorata)", exc_info=True)
        return False


def recent(limit: int = 50) -> list[dict]:
    """Ultimi eventi (più recenti prima) per una vista admin. [] se disattivo/errore."""
    if not enabled():
        return []
    limit = max(1, min(int(limit or 50), 500))
    try:
        with tenants._conn() as c:
            with c.cursor() as cur:
                cur.execute(
                    "SELECT kind, scope, question, created_at FROM analytics_events "
                    "ORDER BY created_at DESC LIMIT %s",
                    (limit,),
                )
                rows = cur.fetchall()
        return [
            {"kind": r[0], "scope": r[1], "question": r[2],
             "at": r[3].isoformat() if hasattr(r[3], "isoformat") else str(r[3])}
            for r in rows
        ]
    except Exception:  # pragma: no cover
        log.warning("lettura eventi analytics fallita (ignorata)", exc_info=True)
        return []
