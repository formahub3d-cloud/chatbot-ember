"""V9/D · La conversazione che dura: riassunti compressi (audit-2026-08-02-48).

L'area «conversazione» è ferma a 6/10 e le sue parti ci sono quasi tutte: il tono
per tutti, il muro che diventa porta, il filo che espande la domanda di seguito,
la memoria delle preferenze. Manca il pezzo che le tiene insieme — **una
conversazione che dura**: cambiare argomento e tornare indietro, riprendere una
cosa di ieri, dire «no, intendevo l'altro». Soprattutto a voce, dove riformulare
tutto ogni volta è innaturale.

La strada era già scritta nella task ‑42: **riassunti compressi**. Zoey li chiama
*epoch summaries* ed è l'unica cosa architetturalmente interessante del loro
prodotto — invece di tenere tutti i turni, si comprime la conversazione in un
riassunto richiamabile.

**Quando si scrive: una volta, a fine conversazione.** Non a ogni domanda. È
questo che lo rende compatibile con la voce: a 55 ms di prima sillaba, una
chiamata al modello dentro il turno si sentirebbe. Qui la chiamata avviene quando
la conversazione è finita, e nessuno sta aspettando una risposta.

Come si sa che è finita: lo dice il client (`POST /chat/chiudi`) — la console
quando chiudi il pannello o ne apri una nuova, il widget quando la pagina si
chiude. Non c'è una spazzatura periodica che compatti i fili scaduti, e non fingo
che ci sia: sarebbe un lavoro schedulato, e questo motore non ne ha ancora uno.
Un filo che muore senza che nessuno chiuda la conversazione resta non compresso —
è un buco dichiarato, non un difetto nascosto.

## I due limiti, tassativi

1. **Il riassunto NON allarga i permessi.** Vale identico al filo (V7/A1): uno
   scope toccato ieri non dà diritti oggi. Il riassunto entra nel prompt come
   contesto su cosa ci si è detti, mai come contenuto citabile e mai come filtro;
   i grant si ricalcolano sempre dalla chiave. C'è un test che lo dimostra, e
   vale più della funzione.
2. **Il riassunto È un dato personale.** Retention dichiarata (30 giorni) e
   applicata in lettura e in scrittura, e soprattutto **raggiungibile dal
   «Dimentica»** della pagina «Cosa so di te» (audit-2026-08-02-49): se il
   bottone non ci arriva, l'articolo 17 è coperto a metà — e mezza copertura, su
   un obbligo di legge, è peggio di nessuna promessa.

Persistenza: tabella `conversation_summary` (`db/conversation_summary.sql`)
quando Supabase è configurato, altrimenti in RAM. La migrazione NON è un
prerequisito e `degrado.per("riassunti")` la dichiara dove si usa.
"""
from __future__ import annotations

import logging
import time
import uuid
from threading import Lock

from . import tenants
from .config import settings
from .providers import chat
from .security import cap_input, redact_pii

log = logging.getLogger("ember.riassunti")

RETENTION_GIORNI = 30       # dichiarata, e applicata: non è una frase nel DPA
MAX_PER_TENANT = 40         # quanti se ne tengono: oltre, i più vecchi cadono
MAX_TESTO = 900             # un riassunto lungo non è un riassunto
MIN_TURNI = 4               # sotto, non c'è una conversazione da comprimere
NEL_PROMPT = 3              # quanti se ne richiamano: gli ultimi, non tutti

_lock = Lock()
_mem: list[dict] = []


def enabled() -> bool:
    return (settings.grants_backend.strip().lower() == "supabase"
            and bool(settings.database_url.strip()))


def _ora() -> float:
    return time.time()


def _iso(v) -> str:
    if not v:
        return ""
    return v.isoformat() if hasattr(v, "isoformat") else str(v)


_PROMPT = """Comprimi questa conversazione in un promemoria per te stesso: cosa si stava
facendo, a che punto si è arrivati, cosa è rimasto in sospeso.

Regole:
- da 2 a 5 righe, non di più. Se non c'è niente da ricordare, rispondi con una riga sola: NIENTE
- scrivi i FATTI e le decisioni, non il riassunto del dialogo («l'utente ha chiesto…» no).
- NIENTE dati personali: nomi di persone, email, telefoni, indirizzi, codici.
- non inventare conclusioni: se una cosa è rimasta aperta, scrivi che è rimasta aperta.

CONVERSAZIONE:
{testo}
"""


def _testo(turni) -> str:
    righe = []
    for t in list(turni or [])[-40:]:
        if not isinstance(t, dict):
            continue
        c = (t.get("content") or "").strip()
        if c:
            righe.append(f"{'Utente' if t.get('role') == 'user' else 'Divina'}: {c[:1200]}")
    return "\n".join(righe)


def comprimi(tenant_code: str, conversazione: str, turni) -> dict | None:
    """Scrive UN riassunto della conversazione. None se non c'è niente da
    comprimere, se il modello non risponde o se il testo conterrebbe PII.

    Sui dati personali la scelta è la stessa di `learned.py`: si SCARTA, non si
    redige. Un promemoria con dentro «[email]» è peggio di un promemoria che non
    esiste — e questo, a differenza di una nota, nessuno lo rileggerà mai per
    accorgersi che è mutilato."""
    tenant_code = (tenant_code or "").strip()
    conversazione = cap_input(conversazione, 80).strip()
    if not tenant_code or not conversazione:
        return None
    testo = _testo(turni)
    if not testo or len([t for t in (turni or []) if isinstance(t, dict)]) < MIN_TURNI:
        return None
    try:
        raw = chat("Rispondi in italiano, senza preamboli.", _PROMPT.format(testo=testo))
    except Exception:
        log.warning("riassunti: il modello non ha risposto")
        return None
    r = cap_input(str(raw or "").strip(), MAX_TESTO)
    if not r or r.strip().upper().startswith("NIENTE"):
        return None
    if redact_pii(r) != r:
        log.info("riassunti: scartato (dati personali nel riassunto)")
        return None
    return _salva(tenant_code, conversazione, r)


def _salva(tenant_code: str, conversazione: str, testo: str) -> dict | None:
    if enabled():
        try:
            with tenants._conn() as c:
                with c.cursor() as cur:
                    cur.execute(
                        "INSERT INTO conversation_summary (tenant_code, conversazione, testo) "
                        "VALUES (%s,%s,%s) ON CONFLICT (tenant_code, conversazione) "
                        "DO UPDATE SET testo=EXCLUDED.testo, created_at=now() "
                        "RETURNING sum_id, created_at", (tenant_code, conversazione, testo))
                    row = cur.fetchone()
                c.commit()
            return {"id": str(row[0]), "tenant": tenant_code, "conversazione": conversazione,
                    "testo": testo, "created_at": _iso(row[1])}
        except Exception:
            log.warning("riassunti: scrittura DB fallita, fallback memoria", exc_info=True)
    with _lock:
        for r in _mem:
            if r["tenant"] == tenant_code and r["conversazione"] == conversazione:
                r.update(testo=testo, created_at=_ora())
                return dict(r)
        r = {"id": uuid.uuid4().hex, "tenant": tenant_code, "conversazione": conversazione,
             "testo": testo, "created_at": _ora()}
        _mem.append(r)
        del _mem[:max(0, len([x for x in _mem if x["tenant"] == tenant_code]) - MAX_PER_TENANT)]
    return dict(r)


def _scaduto(quando) -> bool:
    if isinstance(quando, (int, float)):
        return (_ora() - quando) > RETENTION_GIORNI * 86400
    return False


def elenco(tenant_code: str, limite: int = MAX_PER_TENANT) -> list[dict]:
    """I riassunti vivi di questo tenant, più recenti prima.

    La retention si applica QUI, in lettura, oltre che con la cancellazione a
    monte: una riga scaduta non deve poter comparire nemmeno se la pulizia non è
    ancora passata. È la differenza fra una promessa e un comportamento."""
    tenant_code = (tenant_code or "").strip()
    if not tenant_code:
        return []
    if enabled():
        try:
            with tenants._conn() as c:
                with c.cursor() as cur:
                    cur.execute(
                        "SELECT sum_id, conversazione, testo, created_at "
                        "FROM conversation_summary WHERE tenant_code=%s "
                        "AND created_at > now() - interval '%s days' "
                        "ORDER BY created_at DESC LIMIT %s",
                        (tenant_code, RETENTION_GIORNI, limite))
                    return [{"id": str(r[0]), "tenant": tenant_code, "conversazione": r[1],
                             "testo": r[2], "created_at": _iso(r[3])} for r in cur.fetchall()]
        except Exception:
            log.warning("riassunti: lettura DB fallita, fallback memoria", exc_info=True)
    with _lock:
        vivi = [dict(r) for r in _mem
                if r["tenant"] == tenant_code and not _scaduto(r["created_at"])]
    return sorted(vivi, key=lambda r: r["created_at"], reverse=True)[:limite]


def per_prompt(tenant_code: str, escludi: str = "") -> list[str]:
    """Gli ultimi riassunti da mettere davanti al modello.

    Si esclude la conversazione IN CORSO: il suo contesto è già il filo, e
    ricordarle il proprio riassunto la farebbe girare su se stessa."""
    return [r["testo"] for r in elenco(tenant_code, NEL_PROMPT + 1)
            if r["conversazione"] != escludi][:NEL_PROMPT]


def dimentica(sum_id: str, da: str = "") -> bool:
    """Cancella DAVVERO un riassunto (audit-2026-08-02-49).

    Stessa scelta di `memoria.dimentica`, e qui senza nemmeno la lapide: una
    riga vuota in un elenco di conversazioni non dice niente a nessuno, e il
    fatto che una conversazione sia stata dimenticata non è un'informazione che
    valga la pena conservare su una persona."""
    sum_id = (sum_id or "").strip()
    if not sum_id:
        return False
    if enabled():
        try:
            with tenants._conn() as c:
                with c.cursor() as cur:
                    cur.execute("DELETE FROM conversation_summary WHERE sum_id::text=%s",
                                (sum_id,))
                    tocca = cur.rowcount
                c.commit()
            return bool(tocca)
        except Exception:
            log.warning("riassunti: cancellazione fallita", exc_info=True)
            return False
    with _lock:
        for i, r in enumerate(_mem):
            if r["id"] == sum_id:
                del _mem[i]
                return True
    return False


def dimentica_tutto(tenant_code: str) -> int:
    """Tutti i riassunti di un tenant. Serve al «dimentica tutto» della pagina e
    alla cancellazione GDPR di un cliente intero."""
    n = 0
    for r in elenco(tenant_code, 500):
        if dimentica(r["id"]):
            n += 1
    return n


def reset() -> None:
    """Solo per i test."""
    with _lock:
        _mem.clear()
