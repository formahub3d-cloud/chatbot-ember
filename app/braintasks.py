"""Coda task PERSISTENTE del cervello (tabella Supabase `brain_tasks`).

Complementare alle task di apprendimento (metrics.learning_tasks): quelle sono
in-memory e RIGENERATE dai segnali (gap/👎), queste sono le task OPERATIVE del
cervello — create dalla console (o in futuro da gap, feedback e agenti) — che
devono sopravvivere al redeploy. È la prima tranche della task di roadmap
«coda-task-persistente» (vedi app/roadmap.py).

Regole (coerenti col resto dell'ecosistema Divina):
  - Persistenza best-effort su Supabase quando configurato (DDL: db/ovyon_tasks.sql);
    altrimenti fallback IN-MEMORY (dev/test): l'API non fallisce mai per la coda.
  - Nessun DELETE: una task si chiude ('fatta') o si archivia ('archiviata'),
    SEMPRE col nome di chi decide (`closed_by`), come le contraddizioni.
  - I titoli/note vanno passati già redatti (niente PII): qui si tronca soltanto.
"""
import logging
import time
import uuid
from threading import Lock

from . import tenants
from .config import settings

log = logging.getLogger("ember.braintasks")

KINDS = {"manuale", "gap", "feedback", "agente"}
CLOSE_STATUSES = {"fatta", "archiviata"}

_lock = Lock()
_mem: list[dict] = []       # fallback quando Supabase è off — si azzera al redeploy


def enabled() -> bool:
    """True se la coda è persistente (backend Supabase configurato)."""
    return (settings.grants_backend.strip().lower() == "supabase"
            and bool(settings.database_url.strip()))


def _clean(s: str, n: int) -> str:
    return (s or "").strip()[:n]


def add(title: str, scope: str = "", note: str = "", kind: str = "manuale") -> dict | None:
    """Crea una task aperta. Ritorna la task creata o None (titolo vuoto / errore DB).
    `kind` fuori catalogo → 'manuale'."""
    title = _clean(title, 200)
    if not title:
        return None
    kind = kind if kind in KINDS else "manuale"
    scope, note = _clean(scope, 60), _clean(note, 400)
    if enabled():
        try:
            with tenants._conn() as c:
                with c.cursor() as cur:
                    cur.execute(
                        "INSERT INTO brain_tasks (kind, scope, title, note) "
                        "VALUES (%s,%s,%s,%s) RETURNING task_id, created_at",
                        (kind, scope or None, title, note or None))
                    row = cur.fetchone()
                c.commit()
            return {"id": str(row[0]), "kind": kind, "scope": scope, "title": title,
                    "note": note, "status": "aperta",
                    "created_at": row[1].isoformat() if hasattr(row[1], "isoformat") else str(row[1])}
        except Exception:  # pragma: no cover - best-effort, mai bloccante
            log.warning("brain_tasks: insert fallito (ignorato)", exc_info=True)
            return None
    t = {"id": uuid.uuid4().hex, "kind": kind, "scope": scope, "title": title,
         "note": note, "status": "aperta",
         "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    with _lock:
        _mem.append(t)
    return dict(t)


def list_open(limit: int = 100) -> list[dict]:
    """Task aperte, più recenti prima. [] in caso di errore."""
    limit = max(1, min(int(limit or 100), 500))
    if enabled():
        try:
            with tenants._conn() as c:
                with c.cursor() as cur:
                    cur.execute(
                        "SELECT task_id, kind, scope, title, note, status, created_at "
                        "FROM brain_tasks WHERE status = 'aperta' "
                        "ORDER BY created_at DESC LIMIT %s", (limit,))
                    rows = cur.fetchall()
            return [{"id": str(r[0]), "kind": r[1], "scope": r[2] or "",
                     "title": r[3], "note": r[4] or "", "status": r[5],
                     "created_at": r[6].isoformat() if hasattr(r[6], "isoformat") else str(r[6])}
                    for r in rows]
        except Exception:  # pragma: no cover
            log.warning("brain_tasks: lettura fallita (ignorata)", exc_info=True)
            return []
    with _lock:
        return [dict(t) for t in reversed(_mem) if t["status"] == "aperta"][:limit]


def close(task_id: str, by: str, status: str = "fatta") -> bool:
    """Chiude una task ('fatta' | 'archiviata') col nome di chi decide (obbligatorio,
    come resolved_by delle contraddizioni). Mai DELETE. False se non trovata/aperta."""
    by = _clean(by, 80)
    if not by or status not in CLOSE_STATUSES or not (task_id or "").strip():
        return False
    if enabled():
        try:
            with tenants._conn() as c:
                with c.cursor() as cur:
                    cur.execute(
                        "UPDATE brain_tasks SET status=%s, closed_by=%s, closed_at=now() "
                        "WHERE task_id=%s::uuid AND status='aperta'",
                        (status, by, task_id))
                    n = cur.rowcount
                c.commit()
            return bool(n and n > 0)
        except Exception:  # pragma: no cover
            log.warning("brain_tasks: chiusura fallita (ignorata)", exc_info=True)
            return False
    with _lock:
        for t in _mem:
            if t["id"] == task_id and t["status"] == "aperta":
                t["status"], t["closed_by"] = status, by
                t["closed_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                return True
    return False


def reset() -> None:
    """Solo per i test (fallback in-memory)."""
    with _lock:
        _mem.clear()
