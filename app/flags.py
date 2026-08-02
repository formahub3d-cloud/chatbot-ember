"""V5 · I permessi per-tenant che vivono sul SERVER, non nel browser.

Il permesso più delicato del sistema stava in localStorage: una riga di
JavaScript in una console del browser e il guardrail spariva. Ora è come
`owner`: uno stato che il server conosce e APPLICA — la spunta nel pannello
è la vista, non lo stato. Default: SPENTO, anche per i pannelli cliente.

Due inquilini, stessa famiglia:
  - `liv3`   — «cancellare e agire fuori» (azioni con effetto esterno);
  - `libera` — «conoscenza generale fuori dal vault» (V6/B2). Il TONO della
    conversazione vale per tutti; il CONTENUTO fuori dal cervello no: il
    widget sul sito di un cliente non può inventare sul cliente. Perciò è
    una spunta sul record del tenant, mai una scelta nella richiesta.
  - `buchi`  — «il cliente vede le domande rimaste senza risposta» (V8/B3).
    Quelle domande le hanno fatte i SUOI utenti finali: sono dati dei clienti
    del cliente, e il motore gira ancora in US West. Mostrarle è una cosa che
    si decide con lui, non un default — quindi spento, come gli altri.

Persistenza best-effort su Supabase (db/tenant_flags.sql + tenant_flags_libera.sql)
con fallback in-memory (dev/test), stesso stampo di braintasks.
"""
import logging
from threading import Lock

from . import tenants
from .config import settings

log = logging.getLogger("ember.flags")

_lock = Lock()
_mem: dict[str, dict] = {}      # fallback quando Supabase è off


def enabled() -> bool:
    return (settings.grants_backend.strip().lower() == "supabase"
            and bool(settings.database_url.strip()))


_COLS = ("liv3", "libera", "buchi")      # whitelist: il nome colonna non arriva mai da fuori


def _get(tenant_code: str, col: str) -> bool:
    """Legge un flag. Assente (o lettura fallita) = SPENTO: il default è il freno."""
    tenant_code = (tenant_code or "").strip()
    if not tenant_code or col not in _COLS:
        return False
    if enabled():
        try:
            with tenants._conn() as c:
                with c.cursor() as cur:
                    cur.execute(f"SELECT {col} FROM tenant_flags WHERE tenant_code=%s",
                                (tenant_code,))
                    row = cur.fetchone()
            return bool(row and row[0])
        except Exception:  # pragma: no cover - best-effort: in dubbio, freno
            log.warning("tenant_flags: lettura %s fallita → SPENTO", col, exc_info=True)
            return False
    with _lock:
        return bool(_mem.get(tenant_code, {}).get(col))


def _set(tenant_code: str, col: str, on: bool, by: str) -> bool:
    """Scrive un flag. `by` obbligatorio: è una decisione umana, e si firma."""
    tenant_code, by = (tenant_code or "").strip(), (by or "").strip()[:80]
    if not tenant_code or not by or col not in _COLS:
        return False
    if enabled():
        try:
            with tenants._conn() as c:
                with c.cursor() as cur:
                    cur.execute(
                        f"INSERT INTO tenant_flags (tenant_code, {col}, updated_by, updated_at) "
                        f"VALUES (%s,%s,%s,now()) "
                        f"ON CONFLICT (tenant_code) DO UPDATE SET {col}=EXCLUDED.{col}, "
                        "updated_by=EXCLUDED.updated_by, updated_at=now()",
                        (tenant_code, bool(on), by))
                c.commit()
            return True
        except Exception:  # pragma: no cover
            log.warning("tenant_flags: scrittura %s fallita", col, exc_info=True)
            return False
    with _lock:
        # MERGE, mai sostituzione: due flag sullo stesso tenant convivono
        # (con l'assegnazione secca, accendere `libera` spegneva `liv3`).
        row = dict(_mem.get(tenant_code) or {})
        row[col] = bool(on)
        row["by"] = by
        _mem[tenant_code] = row
    return True


def liv3(tenant_code: str) -> bool:
    """Il livello 3 del tenant. Assente = SPENTO: il default è il freno."""
    return _get(tenant_code, "liv3")


def set_liv3(tenant_code: str, on: bool, by: str) -> bool:
    """Accende/spegne il livello 3. `by` obbligatorio: è una decisione umana."""
    return _set(tenant_code, "liv3", on, by)


def libera(tenant_code: str) -> bool:
    """B2 · Il tenant può ricevere anche CONOSCENZA GENERALE fuori dal vault
    (sempre marcata ⟦fuori⟧). Assente = SPENTO: il default è la promessa —
    ciò che dice il bot di un cliente viene dal materiale di quel cliente."""
    return _get(tenant_code, "libera")


def set_libera(tenant_code: str, on: bool, by: str) -> bool:
    """Accende/spegne la conoscenza generale per un tenant. `by` obbligatorio."""
    return _set(tenant_code, "libera", on, by)


def buchi(tenant_code: str) -> bool:
    """V8/B3 · Il cliente può vedere le domande a cui il bot non ha saputo
    rispondere sui suoi dati. Assente = SPENTO, e non per prudenza generica:
    quelle domande le hanno scritte i suoi utenti finali. Mostrargliele è un
    accordo, e un accordo si prende — non si eredita da un default."""
    return _get(tenant_code, "buchi")


def set_buchi(tenant_code: str, on: bool, by: str) -> bool:
    """Accende/spegne la vista dei buchi per un tenant. `by` obbligatorio."""
    return _set(tenant_code, "buchi", on, by)


def reset() -> None:
    """Solo per i test (fallback in-memory)."""
    with _lock:
        _mem.clear()
