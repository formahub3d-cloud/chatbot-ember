"""V5 · Il LIVELLO 3 («cancellare e agire fuori») vive sul SERVER, per tenant.

Il permesso più delicato del sistema stava in localStorage: una riga di
JavaScript in una console del browser e il guardrail spariva. Ora è come
`owner`: uno stato che il server conosce e APPLICA — la spunta nel pannello
è la vista, non lo stato. Default: SPENTO, anche per i pannelli cliente.

Persistenza best-effort su Supabase (db/tenant_flags.sql) con fallback
in-memory (dev/test), stesso stampo di braintasks.
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


def liv3(tenant_code: str) -> bool:
    """Il livello 3 del tenant. Assente = SPENTO: il default è il freno."""
    tenant_code = (tenant_code or "").strip()
    if not tenant_code:
        return False
    if enabled():
        try:
            with tenants._conn() as c:
                with c.cursor() as cur:
                    cur.execute("SELECT liv3 FROM tenant_flags WHERE tenant_code=%s",
                                (tenant_code,))
                    row = cur.fetchone()
            return bool(row and row[0])
        except Exception:  # pragma: no cover - best-effort: in dubbio, freno
            log.warning("tenant_flags: lettura fallita → livello 3 SPENTO", exc_info=True)
            return False
    with _lock:
        return bool(_mem.get(tenant_code, {}).get("liv3"))


def set_liv3(tenant_code: str, on: bool, by: str) -> bool:
    """Accende/spegne il livello 3. `by` obbligatorio: è una decisione umana."""
    tenant_code, by = (tenant_code or "").strip(), (by or "").strip()[:80]
    if not tenant_code or not by:
        return False
    if enabled():
        try:
            with tenants._conn() as c:
                with c.cursor() as cur:
                    cur.execute(
                        "INSERT INTO tenant_flags (tenant_code, liv3, updated_by, updated_at) "
                        "VALUES (%s,%s,%s,now()) "
                        "ON CONFLICT (tenant_code) DO UPDATE SET liv3=EXCLUDED.liv3, "
                        "updated_by=EXCLUDED.updated_by, updated_at=now()",
                        (tenant_code, bool(on), by))
                c.commit()
            return True
        except Exception:  # pragma: no cover
            log.warning("tenant_flags: scrittura fallita", exc_info=True)
            return False
    with _lock:
        _mem[tenant_code] = {"liv3": bool(on), "by": by}
    return True


def reset() -> None:
    """Solo per i test (fallback in-memory)."""
    with _lock:
        _mem.clear()
