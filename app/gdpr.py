"""Diritti dell'interessato (GDPR) per tenant: EXPORT (accesso/portabilità) ed
ERASURE (diritto all'oblio).

Legge/scrive su Supabase (`documents`, `analytics_events`) e su Qdrant, filtrando
per `tenant`. L'export DECIFRA `content_encrypted` con `CONTENT_ENC_KEY` — è l'unico
percorso di decifratura a runtime, quindi qui la chiave impostata sul server serve
davvero. Tutte le funzioni sono pensate per essere esposte SOLO ad admin.

Nota sulla portata: gli eventi analytics sono associati allo `scope` del chiamante
(che può includere più segmenti); qui si match-a per uguaglianza o inclusione del
codice tenant, quindi l'export/erasure degli eventi è volutamente inclusivo.
"""
import logging

from qdrant_client.models import Filter, FieldCondition, MatchValue, FilterSelector

from . import crypto, docstore, ingest, tenants
from .config import settings

log = logging.getLogger("ember.gdpr")


def _qfilter(tenant: str) -> Filter:
    return Filter(must=[FieldCondition(key="tenant", match=MatchValue(value=tenant))])


def _decrypt(cell):
    """Decifra una cella content_encrypted; None se vuota, o il grezzo se non
    decifrabile (chiave assente/diversa) — senza mai sollevare."""
    if cell is None:
        return None
    try:
        return crypto.decrypt(cell)
    except Exception:
        return "⚠️ non decifrabile (chiave assente o diversa)"


def export_tenant(tenant: str) -> dict:
    """Tutti i dati che Divina detiene per `tenant`: documenti (corpo decifrato) ed
    eventi analytics. Richiede il backend Supabase attivo."""
    if not docstore.enabled():
        return {"tenant": tenant, "error": "backend Supabase non attivo",
                "documents": [], "events": [], "counts": {"documents": 0, "events": 0}}
    docs, events = [], []
    with tenants._conn() as c:
        with c.cursor() as cur:
            cur.execute(
                "SELECT slug, title, path, tags, content_encrypted "
                "FROM documents WHERE tenant_code=%s ORDER BY slug", (tenant,))
            for slug, title, path, tags, enc in cur.fetchall():
                docs.append({"slug": slug, "title": title, "path": path,
                             "tags": list(tags or []), "content": _decrypt(enc)})
            try:
                cur.execute(
                    "SELECT kind, scope, question, created_at FROM analytics_events "
                    "WHERE scope=%s OR scope LIKE %s ORDER BY created_at DESC LIMIT 1000",
                    (tenant, f"%{tenant}%"))
                for kind, scope, q, at in cur.fetchall():
                    events.append({"kind": kind, "scope": scope, "question": q,
                                   "at": at.isoformat() if hasattr(at, "isoformat") else str(at)})
            except Exception:  # pragma: no cover - analytics_events può non esistere
                pass
    return {"tenant": tenant,
            "counts": {"documents": len(docs), "events": len(events)},
            "documents": docs, "events": events}


def _db_counts(tenant: str) -> dict:
    if not docstore.enabled():
        return {"documents": 0, "events": 0}
    with tenants._conn() as c:
        with c.cursor() as cur:
            cur.execute("SELECT count(*) FROM documents WHERE tenant_code=%s", (tenant,))
            d = cur.fetchone()[0]
            e = 0
            try:
                cur.execute("SELECT count(*) FROM analytics_events WHERE scope=%s OR scope LIKE %s",
                            (tenant, f"%{tenant}%"))
                e = cur.fetchone()[0]
            except Exception:  # pragma: no cover
                pass
    return {"documents": d, "events": e}


def _qcount(tenant: str) -> int:
    try:
        return ingest.client().count(
            collection_name=settings.qdrant_collection,
            count_filter=_qfilter(tenant), exact=True).count
    except Exception:  # pragma: no cover
        return -1


def erase_counts(tenant: str) -> dict:
    """Anteprima (dry-run): cosa verrebbe cancellato."""
    c = _db_counts(tenant)
    return {"tenant": tenant, "documents": c["documents"], "events": c["events"],
            "qdrant_points": _qcount(tenant)}


def erase_tenant(tenant: str) -> dict:
    """Cancella i dati del tenant da Qdrant e Supabase (diritto all'oblio).
    Ritorna il conteggio di ciò che era presente PRIMA della cancellazione."""
    before = erase_counts(tenant)
    try:
        ingest.client().delete(
            collection_name=settings.qdrant_collection,
            points_selector=FilterSelector(filter=_qfilter(tenant)))
    except Exception:  # pragma: no cover
        log.warning("erase: cancellazione Qdrant fallita", exc_info=True)
    if docstore.enabled():
        with tenants._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM documents WHERE tenant_code=%s", (tenant,))
                try:
                    cur.execute("DELETE FROM analytics_events WHERE scope=%s OR scope LIKE %s",
                                (tenant, f"%{tenant}%"))
                except Exception:  # pragma: no cover
                    pass
            conn.commit()
    return {"tenant": tenant, "erased": before}
