"""Il cervello VISTO dal motore — KPI del vault, note recenti, ricerca metadati.

Prima tranche della convergenza console (brief Cowork 2026-07-16, task A1/A2/
A4/A7): il vecchio portale (cervello.formahub.it) mostrava il vault con file
statici rigenerati a mano (brain-stats.json, note-index.json); qui gli stessi
dati arrivano VIVI dalla tabella Supabase `documents`, che l'ingest sincronizza
già a ogni giro (app/docstore.py). Niente nuova pipeline: se l'ingest gira, il
cervello in console è aggiornato.

Espone (via /admin/brain*): statistiche del vault (note, aree, ultimi 7 giorni,
ultima ingest), le note più recenti e la ricerca sui metadati (titolo/slug/path).
La ricerca SEMANTICA sul contenuto resta su POST /search (per-tenant, scoped).
Best-effort: senza Supabase risponde vuoto (`persist:false`), mai un errore.

Nota sinapsi: i [[link]] tra note non sono in `documents` — il grafo con le
sinapsi reali arriverà con brain-graph.json pubblicato dalla pipeline del vault
(tranche 2). Qui i nodi sono reali; i collegamenti visivi in console sono per
vicinanza d'area, dichiarati come tali.
"""
import logging

from . import tenants
from .config import settings

log = logging.getLogger("ember.brain")


def enabled() -> bool:
    return (settings.grants_backend.strip().lower() == "supabase"
            and bool(settings.database_url.strip()))


def stats() -> dict:
    """KPI del vault dai metadati sincronizzati. Vuoto (zeri) se backend off."""
    out = {"notes": 0, "areas": 0, "recent_7d": 0, "last_ingest": None, "by_tenant": {}}
    if not enabled():
        return out
    try:
        with tenants._conn() as c:
            with c.cursor() as cur:
                cur.execute("SELECT count(*), count(distinct tenant_code), max(updated_at) FROM documents")
                n, areas, last = cur.fetchone()
                cur.execute("SELECT count(*) FROM documents WHERE updated_at > now() - interval '7 days'")
                recent = cur.fetchone()[0]
                cur.execute("SELECT tenant_code, count(*) FROM documents "
                            "GROUP BY tenant_code ORDER BY count(*) DESC")
                by_tenant = {r[0]: r[1] for r in cur.fetchall()}
        out.update(notes=int(n or 0), areas=int(areas or 0), recent_7d=int(recent or 0),
                   last_ingest=last.isoformat() if hasattr(last, "isoformat") else last,
                   by_tenant=by_tenant)
    except Exception:  # pragma: no cover - best-effort, mai bloccante
        log.warning("brain: lettura stats fallita (ignorata)", exc_info=True)
    return out


def notes(q: str = "", limit: int = 50) -> list[dict]:
    """Note del vault (metadati), più recenti prima. Con `q`: ricerca case-insensitive
    su titolo/slug/path (l'equivalente dell'esploratore ⌘K del vecchio pannello).
    [] se backend off o errore."""
    if not enabled():
        return []
    limit = max(1, min(int(limit or 50), 400))
    q = (q or "").strip()[:80]
    try:
        with tenants._conn() as c:
            with c.cursor() as cur:
                if q:
                    like = f"%{q}%"
                    cur.execute(
                        "SELECT slug, title, path, tenant_code, updated_at FROM documents "
                        "WHERE title ILIKE %s OR slug ILIKE %s OR path ILIKE %s "
                        "ORDER BY updated_at DESC LIMIT %s", (like, like, like, limit))
                else:
                    cur.execute(
                        "SELECT slug, title, path, tenant_code, updated_at FROM documents "
                        "ORDER BY updated_at DESC LIMIT %s", (limit,))
                rows = cur.fetchall()
        return [{"slug": r[0], "title": r[1] or r[0], "path": r[2], "tenant": r[3],
                 "updated_at": r[4].isoformat() if hasattr(r[4], "isoformat") else str(r[4])}
                for r in rows]
    except Exception:  # pragma: no cover
        log.warning("brain: lettura note fallita (ignorata)", exc_info=True)
        return []
