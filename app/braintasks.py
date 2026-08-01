"""Coda task PERSISTENTE del cervello (tabella Supabase `brain_tasks`).

Complementare alle task di apprendimento (metrics.learning_tasks): quelle sono
in-memory e RIGENERATE dai segnali (gap/👎), queste sono le task OPERATIVE del
cervello — create dalla console (o in futuro da gap, feedback e agenti) — che
devono sopravvivere al redeploy. È la prima tranche della task di roadmap
«coda-task-persistente» (vedi app/roadmap.py).

Regole (coerenti col resto dell'ecosistema Divina):
  - Persistenza best-effort su Supabase quando configurato (DDL: db/brain_tasks.sql);
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

KINDS = {"manuale", "gap", "feedback", "agente", "azione", "audit"}   # audit: M2, le task nate dagli audit del pannello
CLOSE_STATUSES = {"fatta", "archiviata"}
# La PRIORITÀ (31-07 sera): 'media' è il default e significa «non ancora
# giudicata», non «bassa». Si dichiara alla nascita o si assegna dopo
# (set_priorita / transition) — mai inferita in automatico.
PRIORITA = ("alta", "media", "bassa")

# ── Macchina a stati (Z2, brief 2026-07-17) ──────────────────────────────────
# aperta(pending) → in-approvazione(awaiting_approval) → approvata(approved) →
# in-esecuzione(executing) → fatta(done) | fallita(failed) | archiviata(archived).
# Le azioni con effetto esterno nascono 'in-approvazione' e NON partono mai
# senza l'ok dell'owner (approved_by). Mai DELETE: si archivia.
# V7/C · «da-verificare» è lo stato del merge: il lavoro c'è, ma nessuno l'ha
# ancora guardato. È l'unico stato che una macchina può assegnare da sola, e da
# lì non si esce senza una persona che ci metta il nome.
OPEN_STATUSES = ("aperta", "in-approvazione", "approvata", "in-esecuzione", "da-verificare")
TRANSITIONS = {
    "aperta":          {"fatta", "archiviata", "in-approvazione", "da-verificare"},
    "in-approvazione": {"approvata", "archiviata"},
    "approvata":       {"in-esecuzione", "archiviata"},
    "in-esecuzione":   {"fatta", "fallita", "da-verificare"},
    "da-verificare":   {"fatta", "archiviata", "aperta"},   # «l'ho guardata»: sì, no, torna indietro
}
_NEEDS_BY = {"approvata", "fatta", "archiviata"}   # decisioni umane: nome obbligatorio
# «da-verificare» NON è in _NEEDS_BY di proposito: è l'unica transizione che il
# merge può fare senza una firma, perché non afferma che sia fatta — afferma
# soltanto che qualcuno dovrebbe guardarla.

_lock = Lock()
_mem: list[dict] = []       # fallback quando Supabase è off — si azzera al redeploy


def enabled() -> bool:
    """True se la coda è persistente (backend Supabase configurato)."""
    return (settings.grants_backend.strip().lower() == "supabase"
            and bool(settings.database_url.strip()))


def _clean(s: str, n: int) -> str:
    return (s or "").strip()[:n]


def add(title: str, scope: str = "", note: str = "", kind: str = "manuale",
        status: str = "aperta", idempotency_key: str = "",
        priorita: str = "media") -> dict | None:
    """Crea una task. `status` ammesso alla nascita: 'aperta' (backlog) o
    'in-approvazione' (azione che aspetta l'ok dell'owner). `idempotency_key`:
    la stessa azione non si accoda due volte (ritorna quella esistente).
    Ritorna la task o None (titolo vuoto / status non ammesso / errore DB)."""
    title = _clean(title, 200)
    if not title or status not in ("aperta", "in-approvazione"):
        return None
    kind = kind if kind in KINDS else "manuale"
    priorita = priorita if priorita in PRIORITA else "media"
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
                        "INSERT INTO brain_tasks (kind, scope, title, note, status, idempotency_key, priorita) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING task_id, created_at",
                        (kind, scope or None, title, note or None, status, ikey, priorita))
                    row = cur.fetchone()
                c.commit()
            return {"id": str(row[0]), "kind": kind, "scope": scope, "title": title,
                    "note": note, "status": status, "priorita": priorita,
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
             "priorita": priorita,
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
                        "approved_by, error, closed_at, closed_by, priorita, idempotency_key "
                        "FROM brain_tasks WHERE status = ANY(%s) "
                        "ORDER BY created_at DESC LIMIT %s", (list(wanted), limit))
                    rows = cur.fetchall()
            # closed_at/closed_by: senza, le task chiuse spariscono dal racconto.
            # idempotency_key: gli script per-chiave risolvono l'id SENZA creare.
            return [{"id": str(r[0]), "kind": r[1], "scope": r[2] or "",
                     "title": r[3], "note": r[4] or "", "status": r[5],
                     "created_at": r[6].isoformat() if hasattr(r[6], "isoformat") else str(r[6]),
                     "approved_by": r[7] or "", "error": r[8] or "",
                     "closed_at": (r[9].isoformat() if hasattr(r[9], "isoformat") else str(r[9])) if r[9] else "",
                     "closed_by": r[10] or "", "priorita": r[11] or "media",
                     "idempotency_key": r[12] or ""}
                    for r in rows]
        except Exception:  # pragma: no cover
            log.warning("brain_tasks: lettura fallita (ignorata)", exc_info=True)
            return []
    with _lock:
        return [dict(t) for t in reversed(_mem) if t["status"] in wanted][:limit]


def get(task_id: str) -> dict | None:
    """Una task per id — il minimo che serve ai GUARDRAIL (kind, scope,
    status). None = assente. Su errore di lettura ALZA RuntimeError invece di
    tacere: chi fa da freno deve distinguere «non c'è» da «non so» — in
    dubbio, freno (V5c, revisione 1/08 notte)."""
    task_id = (task_id or "").strip()
    if not task_id:
        return None
    if enabled():
        try:
            with tenants._conn() as c:
                with c.cursor() as cur:
                    # confronto su ::text (non cast del parametro a uuid): un id
                    # malformato deve dare «assente», non un errore di cast
                    cur.execute("SELECT task_id::text, kind, scope, status "
                                "FROM brain_tasks WHERE task_id::text = %s", (task_id,))
                    row = cur.fetchone()
        except Exception as e:
            raise RuntimeError("brain_tasks: lettura task fallita") from e
        if not row:
            return None
        return {"id": row[0], "kind": row[1], "scope": row[2], "status": row[3]}
    with _lock:
        for t in _mem:
            if t["id"] == task_id:
                return {"id": t["id"], "kind": t.get("kind"),
                        "scope": t.get("scope"), "status": t.get("status")}
    return None


def annota(task_id: str, note: str) -> bool:
    """Aggiunge una nota a una task SENZA muoverla di stato.

    Simmetrica a `set_priorita`: ci sono cose che si scrivono su una task senza
    che sia successo niente allo stato — «questa è il doppione di quell'altra»,
    «misurato oggi: 55 ms». Prima l'unico modo era una transizione, e una
    transizione finta sporca la storia della task."""
    note = _clean(note, 400)
    if not (task_id or "").strip() or not note:
        return False
    if enabled():
        return _solo_nota(task_id, note)
    with _lock:
        for t in _mem:
            if t["id"] == task_id:
                t["note"] = ((t.get("note") or "") + ("\n" if t.get("note") else "") + note)[:800]
                return True
    return False


def by_idempotency_key(chiave: str) -> dict | None:
    """La task con quella `idempotency_key` (V7/C: il merge cita le CHIAVI, non
    gli id — gli id cambiano fra ambienti, le chiavi no). None se assente.

    Non crea niente: se la chiave non esiste, non esiste — una PR può nominare
    una task di un altro repo, e inventarla sarebbe peggio che ignorarla."""
    chiave = (chiave or "").strip()
    if not chiave:
        return None
    if enabled():
        try:
            with tenants._conn() as c:
                with c.cursor() as cur:
                    cur.execute("SELECT task_id::text, kind, scope, status, title "
                                "FROM brain_tasks WHERE idempotency_key = %s", (chiave,))
                    row = cur.fetchone()
        except Exception as e:
            raise RuntimeError("brain_tasks: lettura per chiave fallita") from e
        if not row:
            return None
        return {"id": row[0], "kind": row[1], "scope": row[2],
                "status": row[3], "title": row[4]}
    with _lock:
        for t in _mem:
            if t.get("idempotency_key") == chiave:
                return {"id": t["id"], "kind": t.get("kind"), "scope": t.get("scope"),
                        "status": t.get("status"), "title": t.get("title")}
    return None


def set_priorita(task_id: str, priorita: str) -> bool:
    """Assegna la priorità a una task esistente, SENZA muoverla di stato:
    la priorità è un giudizio, non una transizione. False se valore o task
    non validi."""
    if priorita not in PRIORITA or not (task_id or "").strip():
        return False
    if enabled():
        try:
            with tenants._conn() as c:
                with c.cursor() as cur:
                    cur.execute("UPDATE brain_tasks SET priorita=%s WHERE task_id=%s::uuid",
                                (priorita, task_id))
                    n = cur.rowcount
                c.commit()
            return bool(n and n > 0)
        except Exception:  # pragma: no cover
            log.warning("brain_tasks: set_priorita fallito (ignorato)", exc_info=True)
            return False
    with _lock:
        for t in _mem:
            if t["id"] == task_id:
                t["priorita"] = priorita
                return True
    return False


def transition(task_id: str, to: str, by: str = "", error: str = "",
               note: str = "", priorita: str = "") -> bool:
    """Muove una task lungo la macchina a stati (TRANSITIONS). Le decisioni umane
    ('approvata', 'fatta', 'archiviata') richiedono `by` (chi decide); 'fallita'
    registra `error`. `note` (opzionale) si AGGIUNGE in coda alla nota esistente:
    lascia sulla task il perché o il numero misurato al momento della decisione,
    senza cancellare la nota di nascita (X1). Mai DELETE. False se transizione
    non valida o task assente."""
    to = (to or "").strip()
    by, error, note = _clean(by, 80), _clean(error, 400), _clean(note, 400)
    priorita = priorita if priorita in PRIORITA else ""
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
            if note:
                sets += ["note = left(coalesce(note,'') || CASE WHEN "
                         "coalesce(note,'')='' THEN '' ELSE E'\n' END || %s, 800)"]
                params += [note]
            if priorita:
                sets += ["priorita=%s"]; params += [priorita]
            params += [task_id, valid_from]
            with tenants._conn() as c:
                with c.cursor() as cur:
                    cur.execute(f"UPDATE brain_tasks SET {', '.join(sets)} "
                                "WHERE task_id=%s::uuid AND status = ANY(%s)", params)
                    n = cur.rowcount
                c.commit()
            return bool(n and n > 0)
        except Exception as e:  # pragma: no cover - DB giù, o CHECK non aggiornato
            # V7/C + regola 1 del giro · «da-verificare» ha bisogno di una
            # migrazione (il CHECK su status). Se non è applicata, il database
            # rifiuta il valore: NON si perde il segnale del merge — la task
            # resta dov'è e si annota che andrebbe verificata, dicendo anche
            # perché lo stato non si è mosso. Il degrado si dichiara, non si
            # subisce (e /admin/status elenca la migrazione mancante).
            if to == "da-verificare" and _check_rifiutato(e):
                log.warning("brain_tasks: stato «da-verificare» rifiutato dal CHECK — "
                            "applica db/brain_tasks_da_verificare.sql. Resto sulla nota.")
                ripiego = ((note + " ") if note else "") + \
                    "[da verificare — stato non applicato: manca db/brain_tasks_da_verificare.sql]"
                return _solo_nota(task_id, ripiego)
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
                if note:
                    t["note"] = ((t.get("note") or "") + ("\n" if t.get("note") else "") + note)[:800]
                if priorita:
                    t["priorita"] = priorita
                return True
    return False


def _check_rifiutato(e: Exception) -> bool:
    """L'errore è «il CHECK non ammette questo valore» (e non un DB giù)?"""
    t = f"{type(e).__name__} {e}".lower()
    return "check" in t and ("constraint" in t or "violat" in t)


def _solo_nota(task_id: str, note: str) -> bool:
    """Attacca una nota senza toccare lo stato. Il ripiego di `transition` quando
    la migrazione dello stato non c'è: meglio una task aperta che dice «guardami»
    che un segnale di merge perso del tutto."""
    if not note:
        return False
    try:
        with tenants._conn() as c:
            with c.cursor() as cur:
                cur.execute(
                    "UPDATE brain_tasks SET note = left(coalesce(note,'') || CASE WHEN "
                    "coalesce(note,'')='' THEN '' ELSE E'\n' END || %s, 800) "
                    "WHERE task_id=%s::uuid", (note, task_id))
                n = cur.rowcount
            c.commit()
        return bool(n and n > 0)
    except Exception:  # pragma: no cover
        log.warning("brain_tasks: nemmeno la nota di ripiego è passata", exc_info=True)
        return False


def claim_next(worker: str = "", kind: str = "") -> dict | None:
    """Z3: un worker prende in carico ATOMICAMENTE la prossima azione approvata
    (approvata → in-esecuzione). Su Supabase usa FOR UPDATE SKIP LOCKED: più
    worker concorrenti non si rubano mai la stessa task (niente doppioni).
    Con `kind` filtra (es. 'azione' = payload strutturato eseguibile: le
    proposte a esecuzione umana, kind 'agente', restano fuori dal claim).
    None se non c'è nulla da eseguire. Fallback in-memory per dev/test."""
    worker = _clean(worker, 60)
    kind = kind if kind in KINDS else ""
    if enabled():
        try:
            with tenants._conn() as c:
                with c.cursor() as cur:
                    cur.execute(
                        "SELECT task_id FROM brain_tasks WHERE status='approvata' "
                        + ("AND kind=%s " if kind else "") +
                        "ORDER BY approved_at NULLS LAST, created_at "
                        "LIMIT 1 FOR UPDATE SKIP LOCKED",
                        ((kind,) if kind else ()))
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
            if t["status"] == "approvata" and (not kind or t["kind"] == kind):
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
