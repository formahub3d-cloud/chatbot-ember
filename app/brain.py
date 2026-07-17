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
import json
import logging
import re
import time
from threading import Lock

from . import tenants
from .config import settings

log = logging.getLogger("ember.brain")

# [[wikilink]] di Obsidian: '[[slug]]', '[[slug|etichetta]]', '[[slug#sezione]]'.
# Stessa grammatica del quality gate del vault (LINK_RE).
_LINK_RE = re.compile(r"\[\[([^\]|#\n]+?)(?:[|#][^\]\n]*)?\]\]")

_glock = Lock()
_mem_graph: dict | None = None      # fallback quando Supabase è off (dev/test)


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


# ── Grafo REALE del cervello: nodi = note, sinapsi = [[link]] ─────────────────
# Costruito dall'ingest completo (che ha in mano il contenuto di ogni nota dopo
# sync_vault) e persistito su Supabase (riga unica jsonb, db/ovyon_graph.sql):
# la console lo disegna nella tab «Cervello vivo» — tranche 2 della convergenza.

def build_graph(notes: list[dict]) -> dict:
    """Nodi e archi dai [[wikilink]]: risoluzione per slug (case-insensitive),
    alias '[[x|label]]' e ancore '[[x#sez]]' gestiti, self-link e duplicati
    scartati. `notes`: dict con slug/title/tenant/content (come notes_meta)."""
    notes = list(notes)[:2000]
    nodes = [{"slug": n.get("slug", ""), "title": n.get("title") or n.get("slug", ""),
              "tenant": n.get("tenant", "")} for n in notes]
    idx: dict[str, int] = {}
    for i, n in enumerate(nodes):
        idx.setdefault(n["slug"].lower(), i)
    seen: set[tuple] = set()
    links: list[list[int]] = []
    for i, n in enumerate(notes):
        for m in _LINK_RE.finditer(n.get("content") or ""):
            j = idx.get(m.group(1).strip().lower())
            if j is None or j == i:
                continue
            key = (min(i, j), max(i, j))
            if key not in seen:
                seen.add(key)
                links.append([key[0], key[1]])
    return {"nodes": nodes, "links": links,
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}


def save_graph(notes: list[dict]) -> int:
    """Ricostruisce il grafo dalle note e lo salva (jsonb riga unica; fallback
    in-memory). Best-effort: mai un'eccezione verso l'ingest. Ritorna il numero
    di sinapsi salvate."""
    global _mem_graph
    g = build_graph(notes)
    with _glock:
        _mem_graph = g
    if enabled():
        try:
            with tenants._conn() as c:
                with c.cursor() as cur:
                    cur.execute(
                        "INSERT INTO brain_graph (id, graph) VALUES (1, %s::jsonb) "
                        "ON CONFLICT (id) DO UPDATE SET graph = EXCLUDED.graph, "
                        "generated_at = now()", (json.dumps(g),))
                c.commit()
        except Exception:  # pragma: no cover - best-effort
            log.warning("brain: salvataggio grafo fallito (resta in-memory)", exc_info=True)
    return len(g["links"])


def graph() -> dict | None:
    """L'ultimo grafo generato (Supabase, poi fallback in-memory). None se mai
    generato: serve una ingest completa."""
    if enabled():
        try:
            with tenants._conn() as c:
                with c.cursor() as cur:
                    cur.execute("SELECT graph FROM brain_graph WHERE id = 1")
                    row = cur.fetchone()
            if row and row[0]:
                return row[0] if isinstance(row[0], dict) else json.loads(row[0])
        except Exception:  # pragma: no cover
            log.warning("brain: lettura grafo fallita (ignorata)", exc_info=True)
    with _glock:
        return _mem_graph


def reset() -> None:
    """Solo per i test."""
    global _mem_graph
    with _glock:
        _mem_graph = None
