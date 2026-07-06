"""Gestione tenant (chiavi → scope permessi).

Sorgenti, in ordine di precedenza a runtime:
  1) Database Postgres (se DATABASE_URL è impostata) — gestibile senza re-deploy.
  2) Variabile TENANTS_JSON (cloud senza DB).
  3) File tenants.json (sviluppo locale).

Il risultato è in cache in memoria per 60s per non interrogare il DB ad ogni richiesta.
Se il DB non risponde, si fa fallback automatico alla sorgente statica.
"""
import json
import logging
import time
from pathlib import Path

from .config import settings

log = logging.getLogger("ember.tenants")

_CACHE: dict = {"data": None, "ts": 0.0}
_TTL = 60.0


def load_static() -> dict:
    """Tenant da TENANTS_JSON (precedenza) o dal file tenants.json."""
    if settings.tenants_json.strip():
        try:
            return json.loads(settings.tenants_json)
        except json.JSONDecodeError:
            log.error("TENANTS_JSON non è JSON valido: ignorato")
    p = Path(__file__).resolve().parent.parent / "tenants.json"
    if p.exists():
        return json.loads(p.read_text("utf-8"))
    return {}


def _conn():
    import psycopg2  # import locale: serve solo quando si usa il DB
    # connect_timeout: evita blocchi lunghi se il pooler non risponde.
    # keepalives: tiene viva la connessione sul pooler (transaction mode),
    # riducendo i drop "a freddo" dopo un periodo di inattività.
    return psycopg2.connect(
        settings.database_url,
        connect_timeout=5,
        keepalives=1, keepalives_idle=30, keepalives_interval=10, keepalives_count=3,
    )


def init_and_seed(seed: dict) -> int:
    """Crea la tabella tenants (se non esiste) e fa upsert delle righe fornite."""
    with _conn() as c:
        with c.cursor() as cur:
            cur.execute(
                "CREATE TABLE IF NOT EXISTS tenants ("
                "key TEXT PRIMARY KEY, name TEXT, allowed_scopes JSONB NOT NULL)"
            )
            for k, v in seed.items():
                cur.execute(
                    "INSERT INTO tenants (key, name, allowed_scopes) VALUES (%s, %s, %s) "
                    "ON CONFLICT (key) DO UPDATE SET name = EXCLUDED.name, "
                    "allowed_scopes = EXCLUDED.allowed_scopes",
                    (k, v.get("name", ""), json.dumps(v["allowed_scopes"])),
                )
        c.commit()
    return len(seed)


def ensure_seeded() -> None:
    """Allo startup: se c'è un DB, crea la tabella `tenants` e — solo se vuota —
    la popola dalla sorgente statica (TENANTS_JSON/file). Idempotente: non tocca
    dati già presenti, così puoi gestire i tenant direttamente nel DB."""
    if _mongo_enabled():
        try:
            n = mongo_seed()
            if n:
                log.info("Mongo tenants popolato: %d tenant", n)
        except Exception:
            log.exception("mongo_seed fallito")
        return
    if not settings.database_url.strip():
        return
    static = load_static()
    with _conn() as c:
        with c.cursor() as cur:
            cur.execute(
                "CREATE TABLE IF NOT EXISTS tenants ("
                "key TEXT PRIMARY KEY, name TEXT, allowed_scopes JSONB NOT NULL)"
            )
            cur.execute("SELECT COUNT(*) FROM tenants")
            count = cur.fetchone()[0]
            if count == 0 and static:
                for k, v in static.items():
                    cur.execute(
                        "INSERT INTO tenants (key, name, allowed_scopes) "
                        "VALUES (%s, %s, %s) ON CONFLICT (key) DO NOTHING",
                        (k, v.get("name", ""), json.dumps(v["allowed_scopes"])),
                    )
                log.info("Tabella tenants popolata: %d tenant", len(static))
        c.commit()


def load_db() -> dict:
    """Tenant dalla tabella Postgres."""
    with _conn() as c:
        with c.cursor() as cur:
            cur.execute("SELECT key, name, allowed_scopes FROM tenants")
            rows = cur.fetchall()
    out = {}
    for k, n, s in rows:
        scopes = s if isinstance(s, list) else json.loads(s)
        out[k] = {"name": n, "allowed_scopes": scopes}
    return out


def get_tenants() -> dict:
    """Mappa tenant con cache 60s + fallback statico se il DB non risponde."""
    now = time.time()
    if _CACHE["data"] is not None and now - _CACHE["ts"] < _TTL:
        return _CACHE["data"]
    if settings.database_url.strip():
        try:
            data = load_db()
        except Exception:
            log.exception("DB tenants non raggiungibile: fallback statico")
            data = load_static()
    else:
        data = load_static()
    _CACHE["data"] = data
    _CACHE["ts"] = now
    return data


# ── MongoDB store (consigliato in produzione) ──────────────────────────
# Chiavi HASHATE (mai in chiaro), quote giornaliere, revoca via `active`.
# Attivo quando MONGO_URI è valorizzata; altrimenti si usa il percorso statico.

def _mongo_enabled() -> bool:
    return bool(settings.mongo_uri.strip())


def _mdb():
    from pymongo import MongoClient  # import locale: serve solo col Mongo
    cli = MongoClient(settings.mongo_uri, serverSelectionTimeoutMS=5000)
    return cli[settings.mongo_db]


def mongo_seed() -> int:
    """Crea l'indice unico su key_hash e — se la collection è vuota — semina i
    tenant dalla sorgente statica (le chiavi in chiaro vengono hashate)."""
    from .security import hash_key
    db = _mdb()
    col = db[settings.tenants_collection]
    col.create_index("key_hash", unique=True)
    if col.estimated_document_count() > 0:
        return 0
    static = load_static()
    docs = []
    for key, v in static.items():
        docs.append({
            "key_hash": hash_key(key),
            "name": v.get("name", ""),
            "allowed_scopes": v.get("allowed_scopes", []),
            "allowed_origins": v.get("allowed_origins", []),
            "branding": v.get("branding", {}),
            "quota_day": int(v.get("quota_day", 0) or 0),
            "active": True,
        })
    if docs:
        col.insert_many(docs)
    return len(docs)


# ── Backend Supabase/Postgres `api_keys` (schema OVYON) ────────────────────────
# Chiavi HASHATE + grant a tre livelli (allowed_orgs/tenants/sub_tenants) + audit
# su access_logs. Attivo quando GRANTS_BACKEND=supabase e DATABASE_URL è valorizzata.

def _apikeys_enabled() -> bool:
    return settings.grants_backend.strip().lower() == "supabase" and bool(settings.database_url.strip())


def _as_list(v) -> list:
    """Normalizza un array Postgres (già lista da psycopg2) in list[str]."""
    if v is None:
        return []
    return list(v) if isinstance(v, (list, tuple)) else [v]


def resolve_key_apikeys(key: str) -> dict | None:
    """Risolve una chiave dalla tabella api_keys (per HASH), con i grant a tre livelli.
    Ritorna None se assente o revocata (active=false). `allowed_scopes` è tenuto in
    sincrono con `allowed_tenants` per retro-compatibilità con rag.build_filter."""
    from .security import hash_key
    import time
    kh = hash_key(key)
    row = None
    last_err = None
    # 1 retry: assorbe il drop "a freddo" del pooler (prima richiesta dopo inattività),
    # che altrimenti farebbe fallback → 401 su una chiave valida. Un vero outage del DB
    # fa fallire entrambi i tentativi e lo gestisce get_tenant_by_key (try/except).
    for attempt in range(2):
        try:
            with _conn() as c:
                with c.cursor() as cur:
                    cur.execute(
                        "SELECT name, active, quota_day, allowed_orgs, allowed_tenants, "
                        "allowed_sub_tenants, allowed_origins, branding FROM api_keys WHERE key_hash = %s",
                        (kh,),
                    )
                    row = cur.fetchone()
            break
        except Exception as e:  # es. OperationalError/InterfaceError su connessione stantia
            last_err = e
            log.warning("api_keys lookup tentativo %d fallito: %s", attempt + 1, e)
            if attempt == 0:
                time.sleep(0.2)
    else:
        raise last_err
    if not row or not row[1]:  # assente o active=false
        return None
    name, _active, quota_day, orgs, tenants_, subs, origins, branding = row
    tenants_ = _as_list(tenants_)
    return {
        "name": name or "",
        "allowed_scopes": tenants_,               # storico == tenant
        "allowed_tenants": tenants_,
        "allowed_orgs": _as_list(orgs),
        "allowed_sub_tenants": _as_list(subs),
        "allowed_origins": _as_list(origins),
        "branding": branding or {},               # jsonb → dict (white-label per tenant)
        "quota_day": int(quota_day or 0),
        "key_hash": kh,
    }


def log_access(key_hash: str, action: str, tenant_code: str | None = None,
               org_code: str | None = None, detail: str | None = None) -> None:
    """Scrive una voce nell'audit trail access_logs. Best-effort: non solleva mai
    (l'audit non deve mai bloccare una richiesta). No-op se il backend non è attivo.

    L'insert gira in una sessione con i GUC ovyon.* dell'attore (rls.session_grants):
    così la policy RLS scope-checked su access_logs (db/ovyon_schema.sql) è rispettata
    anche con un ruolo non privilegiato."""
    if not _apikeys_enabled() or not key_hash:
        return
    try:
        from . import rls  # import ritardato: evita cicli a import-time
        grants = {"allowed_orgs": [org_code] if org_code else [],
                  "allowed_tenants": [tenant_code] if tenant_code else []}
        with rls.session_grants(grants) as (_c, cur):
            cur.execute(
                "INSERT INTO access_logs (key_hash, action, tenant_code, org_code, detail) "
                "VALUES (%s, %s, %s, %s, %s)",
                (key_hash, action, tenant_code, org_code, detail),
            )
    except Exception:
        log.exception("log_access fallito (ignorato)")


def get_tenant_by_key(key: str) -> dict | None:
    """Risolve un tenant dalla sua chiave.
    - Con GRANTS_BACKEND=supabase: lookup per HASH nella tabella api_keys (grant a
      tre livelli). Fallback ai percorsi seguenti se il DB non risponde.
    - Con MONGO_URI: lookup per HASH + controllo `active` (revoca). Le chiavi non
      sono mai confrontate in chiaro.
    - Altrimenti: percorso statico/Postgres (chiave in chiaro), retro-compatibile.
    """
    if not key:
        return None
    if _apikeys_enabled():
        try:
            return resolve_key_apikeys(key)
        except Exception:
            log.exception("api_keys non raggiungibile: fallback")
    if _mongo_enabled():
        from .security import hash_key
        try:
            doc = _mdb()[settings.tenants_collection].find_one({"key_hash": hash_key(key)})
        except Exception:
            log.exception("Mongo tenants non raggiungibile: fallback statico")
            return get_tenants().get(key)
        if not doc or not doc.get("active", True):
            return None
        return {
            "name": doc.get("name", ""),
            "allowed_scopes": doc.get("allowed_scopes", []),
            "allowed_origins": doc.get("allowed_origins", []),
            "branding": doc.get("branding", {}),
            "quota_day": int(doc.get("quota_day", 0) or 0),
            "key_hash": doc.get("key_hash"),
        }
    return get_tenants().get(key)


def _quota_ok_pg(kh: str, limit: int, period: str) -> bool:
    """Contatore quota atomico su Supabase (tabella key_usage), per-periodo.
    Incrementa e confronta col limite. Fail-open in caso di errore."""
    try:
        with _conn() as c:
            with c.cursor() as cur:
                cur.execute(
                    "INSERT INTO key_usage (key_hash, period, count) VALUES (%s,%s,1) "
                    "ON CONFLICT (key_hash, period) DO UPDATE SET count = key_usage.count + 1 "
                    "RETURNING count",
                    (kh, period),
                )
                n = cur.fetchone()[0]
            c.commit()
        return int(n) <= limit
    except Exception:
        log.exception("quota (supabase) fallita: consento (fail-open)")
        return True


def quota_ok(tenant: dict) -> bool:
    """True se il tenant è sotto la quota giornaliera. Contatore atomico per-giorno
    (UTC) su Supabase (key_usage) o, in alternativa, Mongo. quota_day<=0 o nessun
    backend = illimitato. Fail-open in errore."""
    limit = int((tenant or {}).get("quota_day", 0) or 0)
    kh = (tenant or {}).get("key_hash")
    if limit <= 0 or not kh:
        return True
    from datetime import datetime, timezone
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    # Mongo se configurato (setup storico); altrimenti Supabase (backend OVYON live).
    if _mongo_enabled():
        from pymongo import ReturnDocument
        try:
            col = _mdb()[settings.usage_collection]
            doc = col.find_one_and_update(
                {"key_hash": kh, "day": day},
                {"$inc": {"count": 1}},
                upsert=True, return_document=ReturnDocument.AFTER,
            )
            return int(doc.get("count", 1)) <= limit
        except Exception:
            log.exception("quota check (mongo) fallita: consento (fail-open)")
            return True
    if _apikeys_enabled():
        return _quota_ok_pg(kh, limit, day)
    return True
