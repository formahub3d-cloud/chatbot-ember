"""Proposte di auto-miglioramento del cervello — SEZIONE PRIVATA DELL'OWNER.

Il flusso «audit → task» del vecchio portale, ricollegato alla console:
i segnali dell'audit (gap, feedback 👎, stato del sistema) diventano PROPOSTE;
l'owner le vede nella tab riservata della console, le APPROVA o le IGNORA;
le approvate entrano nella coda operativa persistente (brain_tasks) e da lì
si chiudono col nome di chi decide. Niente è automatico: decide sempre l'owner.

Privacy (non negoziabile, collaudo 2026-07-16 task B1): gli endpoint sono SOLO
admin (`_require_admin`, Bearer ADMIN_TOKEN) — mai chiave tenant, mai pubblici.

Le proposte sono DERIVATE (rigenerate a ogni lettura dai segnali correnti);
approvate/ignorate finiscono in una blocklist in-memory: al redeploy una
proposta ignorata può ripresentarsi — meglio riproporre che perdere un segnale.
"""
import hashlib
from threading import Lock

from . import braintasks, events, metrics

_lock = Lock()
_handled: set[str] = set()      # id già approvati o ignorati (in-memory)


def _pid(source: str, scope: str, title: str) -> str:
    """Id stabile della proposta: stesso segnale → stesso id (sopravvive al refresh)."""
    return hashlib.sha1(f"{source}|{scope}|{title}".encode("utf-8")).hexdigest()[:12]


def _candidates() -> list[dict]:
    """Le proposte grezze, dai segnali correnti. Fonti: task di apprendimento
    (gap/👎, già raggruppate e ordinate da metrics.learning_tasks) + audit di
    sistema (persistenze mancanti)."""
    out: list[dict] = []
    for t in metrics.learning_tasks()["tasks"]:
        source = "gap" if t["kind"] == "gap" else "feedback"
        title = (f'Colma il gap: «{t["question"]}»' if source == "gap"
                 else f'Rivedi la risposta: «{t["question"]}»')
        out.append({"source": source, "scope": t["scope"], "title": title,
                    "detail": t["suggestion"], "count": t["count"],
                    "last_at": t["last_at"]})
    if not braintasks.enabled():
        out.append({"source": "sistema", "scope": "",
                    "title": "Attiva la persistenza della coda task",
                    "detail": ("La coda gira in-memory e si azzera al redeploy: applica "
                               "db/ovyon_tasks.sql su Supabase e verifica "
                               "GRANTS_BACKEND=supabase + DATABASE_URL."),
                    "count": 1, "last_at": 0})
    if not events.enabled():
        out.append({"source": "sistema", "scope": "",
                    "title": "Attiva lo storico eventi (ANALYTICS_PERSIST)",
                    "detail": ("Senza persistenza analytics niente trend e insight duraturi: "
                               "imposta ANALYTICS_PERSIST=true col backend Supabase."),
                    "count": 1, "last_at": 0})
    return out


def generate() -> list[dict]:
    """Le proposte ancora da valutare (già approvate/ignorate escluse)."""
    with _lock:
        handled = set(_handled)
    props = []
    for c in _candidates():
        pid = _pid(c["source"], c["scope"], c["title"])
        if pid not in handled:
            props.append({"id": pid, **c})
    return props


def approve(pid: str) -> dict | None:
    """Approva una proposta: crea la task nella coda operativa (brain_tasks) e
    toglie la proposta dalla lista. None se la proposta non esiste (rigenerare)."""
    for p in generate():
        if p["id"] == pid:
            kind = p["source"] if p["source"] in ("gap", "feedback") else "manuale"
            t = braintasks.add(p["title"], scope=p["scope"], note=p["detail"], kind=kind)
            if t is None:
                return None
            with _lock:
                _handled.add(pid)
            return t
    return None


def dismiss(pid: str) -> None:
    """Ignora una proposta (non ricompare finché il processo vive)."""
    pid = (pid or "").strip()
    if pid:
        with _lock:
            _handled.add(pid)


def reset() -> None:
    """Solo per i test."""
    with _lock:
        _handled.clear()
