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
import logging
from threading import Lock

from . import braintasks, events, metrics

log = logging.getLogger("ember.proposals")

_lock = Lock()
_handled: set[str] = set()      # id già approvati o ignorati (in-memory)
# V6/B3 · Le «cose imparate» dalle conversazioni: a differenza delle altre
# proposte NON sono derivate da un segnale che si può ricalcolare — la
# conversazione è passata. Quindi si tengono, in coda, finché l'owner non
# decide. Stessa persistenza best-effort del resto del modulo: in-memory,
# perché una proposta persa è meglio di una nota scritta da sola.
_imparato: list[dict] = []
_MAX_IMPARATO = 60              # tetto: la coda è un posto dove si decide, non un archivio


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
                               "db/brain_tasks.sql su Supabase e verifica "
                               "GRANTS_BACKEND=supabase + DATABASE_URL."),
                    "count": 1, "last_at": 0})
    if not events.enabled():
        out.append({"source": "sistema", "scope": "",
                    "title": "Attiva lo storico eventi (ANALYTICS_PERSIST)",
                    "detail": ("Senza persistenza analytics niente trend e insight duraturi: "
                               "imposta ANALYTICS_PERSIST=true col backend Supabase."),
                    "count": 1, "last_at": 0})
    return out


def add_learned(items, conversazione: str = "") -> list[dict]:
    """V6/B3 · Mette in coda le «cose imparate» proposte da una conversazione.

    NON scrive nel vault: mettere in coda non è salvare — è chiedere. Ogni voce
    porta la sua CITAZIONE (la regola 2 di B3, già imposta in `learned.filtra`):
    qui la si conserva perché arrivi fino alla schermata dove si decide.
    Ritorna le proposte accodate, con il loro id."""
    fuori: list[dict] = []
    with _lock:
        handled = set(_handled)
        gia = {p["id"] for p in _imparato}
        for it in items or []:
            titolo = str(it.get("titolo") or "").strip()
            if not titolo:
                continue
            scope = str(it.get("scope") or "").strip()
            pid = _pid("conversazione", scope, titolo)
            if pid in handled or pid in gia:
                continue
            p = {"id": pid, "source": "conversazione", "scope": scope,
                 "title": f"Impara dalla conversazione: «{titolo}»",
                 "detail": str(it.get("contenuto") or "").strip(),
                 "citazione": str(it.get("citazione") or "").strip(),
                 "conversazione": str(conversazione or "")[:120],
                 "nota_titolo": titolo, "count": 1, "last_at": 0}
            _imparato.append(p)
            gia.add(pid)
            fuori.append(p)
        if len(_imparato) > _MAX_IMPARATO:
            del _imparato[:-_MAX_IMPARATO]
    return fuori


def generate() -> list[dict]:
    """Le proposte ancora da valutare (già approvate/ignorate escluse)."""
    with _lock:
        handled = set(_handled)
        imparato = [p for p in _imparato if p["id"] not in handled]
    props = []
    for c in _candidates():
        pid = _pid(c["source"], c["scope"], c["title"])
        if pid not in handled:
            props.append({"id": pid, **c})
    # le cose imparate in cima: sono l'unica specie che scade con la conversazione
    return imparato + props


def _write_note(p: dict) -> dict | None:
    """B3 · Approvare una «cosa imparata» = scrivere la nota nel vault, MARCATA
    come nata da conversazione (lo marca il server, come in /writeback) e con la
    citazione della sua fonte dentro il corpo. È la conferma umana della regola
    #4: prima non esisteva niente, adesso esiste perché qualcuno ha detto sì."""
    from datetime import datetime, timezone
    from . import writeback
    oggi = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    titolo = p.get("nota_titolo") or p["title"]
    corpo = (f"> Origine: conversazione con Divina · {oggi} · NON verificato\n\n"
             + (p.get("detail") or "").strip()
             + (f"\n\n## Da dove viene\n\n> {p['citazione']}\n" if p.get("citazione") else ""))
    try:
        res = writeback.save_note(p.get("scope") or "", titolo, corpo,
                                  summary="Imparato da una conversazione, da verificare",
                                  tags=["conversazione", "da-verificare"])
    except Exception:  # pragma: no cover - disco/vault non disponibile
        log.warning("proposals: scrittura nota imparata fallita", exc_info=True)
        return None
    return res if res.get("created") else None


def approve(pid: str) -> dict | None:
    """Approva una proposta. Le «cose imparate» diventano una NOTA nel vault
    (marcata, con la citazione); tutte le altre una task nella coda operativa
    (brain_tasks). None se la proposta non esiste (rigenerare) o se la scrittura
    non è andata a buon fine — mai un «fatto» senza il fatto."""
    for p in generate():
        if p["id"] != pid:
            continue
        if p["source"] == "conversazione":
            res = _write_note(p)
            if res is None:
                return None
            with _lock:
                _handled.add(pid)
            return {"nota": res, "kind": "conversazione", "title": p["title"]}
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
        _imparato.clear()
