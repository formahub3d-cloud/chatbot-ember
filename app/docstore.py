"""Sincronizzazione dei METADATI delle note su Supabase (tabella `documents` dello
schema OVYON), in parallelo ai vettori su Qdrant. Abilita la RLS a livello di
documento (Sezione 9): con `documents` popolata, un ruolo non privilegiato +
i GUC ovyon.* vede solo le righe consentite.

Si salvano SOLO metadati (slug/title/path/tags/code a tre livelli): il corpo della
nota resta su Qdrant; `content_encrypted` è riservato alla cifratura a colonna
(fase compliance). Attivo quando GRANTS_BACKEND=supabase e DATABASE_URL sono impostati.
"""
import uuid

from . import tenants
from .config import settings


def enabled() -> bool:
    return settings.grants_backend.strip().lower() == "supabase" and bool(settings.database_url.strip())


def parse_tags(raw) -> list[str]:
    """Normalizza il campo tags (stringa frontmatter '[a, b]' o lista) in list[str]."""
    if isinstance(raw, (list, tuple)):
        return [str(t).strip() for t in raw if str(t).strip()]
    s = (raw or "").strip().strip("[]")
    return [t.strip() for t in s.split(",") if t.strip()]


def content_id_for(path: str) -> str:
    """UUID deterministico dal path relativo: la re-ingest fa upsert, non duplica."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, path))


def _get_or_create(cur, sql: str, params: tuple, cache: dict, key):
    if key in cache:
        return cache[key]
    cur.execute(sql, params)
    val = cur.fetchone()[0]
    cache[key] = val
    return val


def _org_id(cur, code, cache):
    return _get_or_create(
        cur,
        "INSERT INTO organizations (code, name) VALUES (%s, %s) "
        "ON CONFLICT (code) DO UPDATE SET name = organizations.name RETURNING org_id",
        (code, code), cache, code,
    )


def _tenant_id(cur, code, org_id, cache):
    return _get_or_create(
        cur,
        "INSERT INTO tenants (code, org_id, name) VALUES (%s, %s, %s) "
        "ON CONFLICT (code) DO UPDATE SET name = tenants.name RETURNING tenant_id",
        (code, org_id, code), cache, code,
    )


def _sub_id(cur, code, tenant_id, cache):
    return _get_or_create(
        cur,
        "INSERT INTO sub_tenants (code, tenant_id) VALUES (%s, %s) "
        "ON CONFLICT (tenant_id, code) DO UPDATE SET code = sub_tenants.code RETURNING sub_tenant_id",
        (code, tenant_id), cache, (tenant_id, code),
    )


_DOC_UPSERT = (
    "INSERT INTO documents (content_id, sub_tenant_id, tenant_id, org_id, "
    "org_code, tenant_code, sub_code, slug, title, path, type, tags) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
    "ON CONFLICT (content_id) DO UPDATE SET "
    "sub_tenant_id=EXCLUDED.sub_tenant_id, tenant_id=EXCLUDED.tenant_id, "
    "org_id=EXCLUDED.org_id, org_code=EXCLUDED.org_code, tenant_code=EXCLUDED.tenant_code, "
    "sub_code=EXCLUDED.sub_code, slug=EXCLUDED.slug, title=EXCLUDED.title, "
    "path=EXCLUDED.path, tags=EXCLUDED.tags, updated_at=now()"
)


def sync_notes(notes: list[dict]) -> int:
    """Upsert dei metadati nota su Supabase. `notes`: dict con
    org/tenant/sub_tenant/slug/title/path/tags. Ritorna il numero di righe scritte.
    No-op (0) se il backend non è attivo o la lista è vuota."""
    if not enabled() or not notes:
        return 0
    orgs, tnts, subs = {}, {}, {}
    n = 0
    with tenants._conn() as c:
        with c.cursor() as cur:
            for nt in notes:
                org_id = _org_id(cur, nt["org"], orgs)
                tenant_id = _tenant_id(cur, nt["tenant"], org_id, tnts)
                sub_id = _sub_id(cur, nt["sub_tenant"], tenant_id, subs) if nt.get("sub_tenant") else None
                cur.execute(_DOC_UPSERT, (
                    content_id_for(nt["path"]), sub_id, tenant_id, org_id,
                    nt["org"], nt["tenant"], nt.get("sub_tenant"),
                    nt["slug"], nt.get("title", nt["slug"]), nt["path"], "markdown",
                    parse_tags(nt.get("tags")),
                ))
                n += 1
        c.commit()
    return n
