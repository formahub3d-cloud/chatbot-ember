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
    return psycopg2.connect(settings.database_url)


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
