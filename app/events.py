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


def _db_ready() -> bool:
    """Backend Supabase raggiungibile (indipendente da analytics_persist): serve alla
    retention, che può ripulire lo storico anche quando la scrittura è disattivata."""
    return settings.grants_backend.strip().lower() == "supabase" and bool(settings.database_url.strip())


def _retention_window(days: int | None) -> int:
    """Soglia effettiva in giorni: override esplicito o settings.retention_days.
    <= 0 (o backend non pronto) significa retention disattivata."""
    d = settings.retention_days if days is None else days
    return int(d) if (_db_ready() and d and int(d) > 0) else 0


def preview_old(days: int | None = None) -> int:
    """Retention dry-run: quante righe VERREBBERO cancellate da purge_old con la
    stessa soglia/filtro, senza cancellare nulla. 0 se disattivato o in errore.
    Utile per stimare l'impatto prima dell'azione distruttiva (come il dry-run di
    /admin/gdpr/erase)."""
    d = _retention_window(days)
    if not d:
        return 0
    try:
        with tenants._conn() as c:
            with c.cursor() as cur:
                cur.execute(
                    "SELECT count(*) FROM analytics_events "
                    "WHERE created_at < now() - make_interval(days => %s)",
                    (d,))
                row = cur.fetchone()
        return int(row[0]) if row and row[0] else 0
    except Exception:  # pragma: no cover - best-effort, mai bloccante
        log.warning("retention: preview analytics fallito (ignorato)", exc_info=True)
        return 0


def purge_old(days: int | None = None) -> int:
    """Retention GDPR: cancella gli eventi più vecchi di `days` giorni (default
    settings.retention_days). 0/None = disattivato → 0. Best-effort. Ritorna il
    numero di righe cancellate."""
    d = _retention_window(days)
    if not d:
        return 0
    try:
        with tenants._conn() as c:
            with c.cursor() as cur:
                cur.execute(
                    "DELETE FROM analytics_events WHERE created_at < now() - make_interval(days => %s)",
                    (int(d),))
                n = cur.rowcount
            c.commit()
        return n if (n and n > 0) else 0
    except Exception:  # pragma: no cover - best-effort, mai bloccante
        log.warning("retention: purge analytics fallito (ignorato)", exc_info=True)
        return 0


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
