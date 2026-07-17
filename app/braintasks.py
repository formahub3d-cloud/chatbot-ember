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

KINDS = {"manuale", "gap", "feedback", "agente", "azione"}
CLOSE_STATUSES = {"fatta", "archiviata"}

# ── Macchina a stati (Z2, brief 2026-07-17) ──────────────────────────────────
# aperta(pending) → in-approvazione(awaiting_approval) → approvata(approved) →
# in-esecuzione(executing) → fatta(done) | fallita(failed) | archiviata(archived).
# Le azioni con effetto esterno nascono 'in-approvazione' e NON partono mai
# senza l'ok dell'owner (approved_by). Mai DELETE: si archivia.
OPEN_STATUSES = ("aperta", "in-approvazione", "approvata", "in-esecuzione")
TRANSITIONS = {
    "aperta":          {"fatta", "archiviata", "in-approvazione"},
    "in-approvazione": {"approvata", "archiviata"},
    "approvata":       {"in-esecuzione", "archiviata"},
    "in-esecuzione":   {"fatta", "fallita"},
}
_NEEDS_BY = {"approvata", "fatta", "archiviata"}   # decisioni umane: nome obbligatorio

_lock = Lock()
_mem: list[dict] = []       # fallback quando Supabase è off — si azzera al redeploy


def enabled() -> bool:
    """True se la coda è persistente (backend Supabase configurato)."""
    return (settings.grants_backend.strip().lower() == "supabase"
            and bool(settings.database_url.strip()))


def _clean(s: str, n: int) -> str:
    return (s or "").strip()[:n]


def add(title: str, scope: str = "", note: str = "", kind: str = "manuale",
        status: str = "aperta", idempotency_key: str = "") -> dict | None:
    """Crea una task. `status` ammesso alla nascita: 'aperta' (backlog) o
    'in-approvazione' (azione che aspetta l'ok dell'owner). `idempotency_key`:
    la stessa azione non si accoda due volte (ritorna quella esistente).
    Ritorna la task o None (titolo vuoto / status non ammesso / errore DB)."""
    title = _clean(title, 200)
    if not title or status not in ("aperta", "in-approvazione"):
        return None
    kind = kind if kind in KINDS else "manuale"
    scope, note = _clean(scope, 60), _clean(note, 400)
    ikey = _clean(idempotency_key, 120) or None
    if enabled():
        try:
            with tenants._conn() as c:
                with c.cursor() as cur:
                    if ikey:
                        cur.execute("SELECT task_id, status FROM brain_tasks "
                                    "WHERE idempotency_key = %s", (ikey,))
                        row = cur.fetchone()
                        if row:
                            return {"id": str(row[0]), "status": row[1], "title": title,
                                    "kind": kind, "scope": scope, "note": note,
                                    "duplicate": True}
                    cur.execute(
                        "INSERT INTO brain_tasks (kind, scope, title, note, status, idempotency_key) "
                        "VALUES (%s,%s,%s,%s,%s,%s) RETURNING task_id, created_at",
                        (kind, scope or None, title, note or None, status, ikey))
                    row = cur.fetchone()
                c.commit()
            return {"id": str(row[0]), "kind": kind, "scope": scope, "title": title,
                    "note": note, "status": status,
                    "created_at": row[1].isoformat() if hasattr(row[1], "isoformat") else str(row[1])}
        except Exception:  # pragma: no cover - best-effort, mai bloccante
            log.warning("brain_tasks: insert fallito (ignorato)", exc_info=True)
            return None
    with _lock:
        if ikey:
            for t in _mem:
                if t.get("idempotency_key") == ikey:
                    return {**t, "duplicate": True}
        t = {"id": uuid.uuid4().hex, "kind": kind, "scope": scope, "title": title,
             "note": note, "status": status, "idempotency_key": ikey,
             "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        _mem.append(t)
    return dict(t)


def list_open(limit: int = 100, status: str = "") -> list[dict]:
    """Task attive (aperta/in-approvazione/approvata/in-esecuzione), più recenti
    prima; con `status` filtra un singolo stato (anche terminale). [] su errore."""
    limit = max(1, min(int(limit or 100), 500))
    wanted = (status,) if status else OPEN_STATUSES
    if enabled():
        try:
            with tenants._conn() as c:
                with c.cursor() as cur:
                    cur.execute(
                        "SELECT task_id, kind, scope, title, note, status, created_at, "
                        "approved_by, error FROM brain_tasks WHERE status = ANY(%s) "
                        "ORDER BY created_at DESC LIMIT %s", (list(wanted), limit))
                    rows = cur.fetchall()
            return [{"id": str(r[0]), "kind": r[1], "scope": r[2] or "",
                     "title": r[3], "note": r[4] or "", "status": r[5],
                     "created_at": r[6].isoformat() if hasattr(r[6], "isoformat") else str(r[6]),
                     "approved_by": r[7] or "", "error": r[8] or ""}
                    for r in rows]
        except Exception:  # pragma: no cover
            log.warning("brain_tasks: lettura fallita (ignorata)", exc_info=True)
            return []
    with _lock:
        return [dict(t) for t in reversed(_mem) if t["status"] in wanted][:limit]


def transition(task_id: str, to: str, by: str = "", error: str = "") -> bool:
    """Muove una task lungo la macchina a stati (TRANSITIONS). Le decisioni umane
    ('approvata', 'fatta', 'archiviata') richiedono `by` (chi decide); 'fallita'
    registra `error`. Mai DELETE. False se transizione non valida o task assente."""
    to = (to or "").strip()
    by, error = _clean(by, 80), _clean(error, 400)
    if not (task_id or "").strip() or to in _NEEDS_BY and not by:
        return False
    valid_from = [f for f, tos in TRANSITIONS.items() if to in tos]
    if not valid_from:
        return False
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    if enabled():
        try:
            sets, params = ["status=%s"], [to]
            if to == "approvata":
                sets += ["approved_by=%s", "approved_at=now()"]; params += [by]
            if to == "in-esecuzione":
                sets += ["started_at=now()"]
            if to in ("fatta", "fallita", "archiviata"):
                sets += ["closed_by=%s", "closed_at=now()"]; params += [by or "sistema"]
            if to == "fallita" and error:
                sets += ["error=%s"]; params += [error]
            params += [task_id, valid_from]
            with tenants._conn() as c:
                with c.cursor() as cur:
                    cur.execute(f"UPDATE brain_tasks SET {', '.join(sets)} "
                                "WHERE task_id=%s::uuid AND status = ANY(%s)", params)
                    n = cur.rowcount
                c.commit()
            return bool(n and n > 0)
        except Exception:  # pragma: no cover
            log.warning("brain_tasks: transizione fallita (ignorata)", exc_info=True)
            return False
    with _lock:
        for t in _mem:
            if t["id"] == task_id and to in TRANSITIONS.get(t["status"], set()):
                t["status"] = to
                if to == "approvata":
                    t["approved_by"], t["approved_at"] = by, now_iso
                if to == "in-esecuzione":
                    t["started_at"] = now_iso
                if to in ("fatta", "fallita", "archiviata"):
                    t["closed_by"], t["closed_at"] = (by or "sistema"), now_iso
                if to == "fallita" and error:
                    t["error"] = error
                return True
    return False


def claim_next(worker: str = "") -> dict | None:
    """Z3: un worker prende in carico ATOMICAMENTE la prossima azione approvata
    (approvata → in-esecuzione). Su Supabase usa FOR UPDATE SKIP LOCKED: più
    worker concorrenti non si rubano mai la stessa task (niente doppioni).
    None se non c'è nulla da eseguire. Fallback in-memory per dev/test."""
    worker = _clean(worker, 60)
    if enabled():
        try:
            with tenants._conn() as c:
                with c.cursor() as cur:
                    cur.execute(
                        "SELECT task_id FROM brain_tasks WHERE status='approvata' "
                        "ORDER BY approved_at NULLS LAST, created_at "
                        "LIMIT 1 FOR UPDATE SKIP LOCKED")
                    row = cur.fetchone()
                    if not row:
                        c.commit()
                        return None
                    cur.execute(
                        "UPDATE brain_tasks SET status='in-esecuzione', started_at=now() "
                        "WHERE task_id=%s RETURNING task_id, kind, scope, title, note, "
                        "idempotency_key, approved_by", (row[0],))
                    r = cur.fetchone()
                c.commit()
            return {"id": str(r[0]), "kind": r[1], "scope": r[2] or "", "title": r[3],
                    "note": r[4] or "", "idempotency_key": r[5] or "",
                    "approved_by": r[6] or "", "worker": worker}
        except Exception:  # pragma: no cover
            log.warning("brain_tasks: claim fallito (ignorato)", exc_info=True)
            return None
    with _lock:
        for t in _mem:
            if t["status"] == "approvata":
                t["status"] = "in-esecuzione"
                t["started_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                return {**t, "worker": worker}
    return None


def close(task_id: str, by: str, status: str = "fatta") -> bool:
    """Chiusura semplice ('fatta' | 'archiviata') col nome di chi decide — wrapper
    storico sulla macchina a stati (valido dagli stati che lo permettono)."""
    if status not in CLOSE_STATUSES:
        return False
    return transition(task_id, status, by=by)


def reset() -> None:
    """Solo per i test (fallback in-memory)."""
    with _lock:
        _mem.clear()
