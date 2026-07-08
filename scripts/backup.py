#!/usr/bin/env python3
"""backup.py — Backup/DR di Ember: snapshot Qdrant + export tabelle Supabase.

Cosa fa (best-effort, ogni passo è indipendente):
  1. QDRANT   crea uno snapshot server-side della collection (ripristinabile
              dalla console/API Qdrant) e ne stampa il nome.
  2. SUPABASE esporta in JSON le tabelle OVYON (documents, access_logs,
              analytics_events, key_usage, api_keys SENZA hash delle chiavi)
              in backup/AAAA-MM-GG/.

Config dalle stesse variabili d'ambiente dell'app (.env): QDRANT_URL,
QDRANT_API_KEY, QDRANT_COLLECTION, DATABASE_URL.

Uso:  python scripts/backup.py            # tutto
      python scripts/backup.py --qdrant   # solo snapshot Qdrant
      python scripts/backup.py --db       # solo export Supabase

Ripristino: vedi DR-RUNBOOK.md. Solo stdlib + psycopg2 (già dipendenza dell'app).
"""
import json
import os
import sys
import urllib.request
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

OUTDIR = Path("backup") / date.today().isoformat()

# Tabelle esportate. api_keys: SENZA key_hash (il backup non deve contenere
# materiale utilizzabile per impersonare un tenant).
TABLES = {
    "documents": "SELECT * FROM documents",
    "access_logs": "SELECT * FROM access_logs",
    "analytics_events": "SELECT * FROM analytics_events",
    "key_usage": "SELECT * FROM key_usage",
    "api_keys": ("SELECT name, active, quota_day, allowed_orgs, allowed_tenants, "
                 "allowed_sub_tenants, allowed_origins, branding FROM api_keys"),
}


def snapshot_qdrant() -> bool:
    url = os.environ.get("QDRANT_URL", "").rstrip("/")
    coll = os.environ.get("QDRANT_COLLECTION", "cervello")
    if not url:
        print("· qdrant: QDRANT_URL non impostata — salto")
        return False
    req = urllib.request.Request(f"{url}/collections/{coll}/snapshots", method="POST")
    key = os.environ.get("QDRANT_API_KEY", "")
    if key:
        req.add_header("api-key", key)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            body = json.loads(r.read().decode())
        name = (body.get("result") or {}).get("name", "?")
        print(f"✓ qdrant: snapshot creato — {name} (collection {coll})")
        return True
    except Exception as e:
        print(f"✗ qdrant: snapshot fallito — {e}")
        return False


def _json_default(v):
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, (bytes, memoryview)):
        return "<binario omesso>"
    return str(v)


def export_supabase() -> bool:
    dsn = os.environ.get("DATABASE_URL", "")
    if not dsn:
        print("· supabase: DATABASE_URL non impostata — salto")
        return False
    try:
        import psycopg2
        import psycopg2.extras
    except ImportError:
        print("✗ supabase: psycopg2 non installato (pip install -r requirements.txt)")
        return False
    OUTDIR.mkdir(parents=True, exist_ok=True)
    ok = True
    try:
        with psycopg2.connect(dsn) as conn:
            for name, sql in TABLES.items():
                try:
                    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                        cur.execute(sql)
                        rows = [dict(r) for r in cur.fetchall()]
                    dest = OUTDIR / f"{name}.json"
                    dest.write_text(json.dumps(rows, ensure_ascii=False, indent=1,
                                               default=_json_default), "utf-8")
                    print(f"✓ supabase: {name} → {dest} ({len(rows)} righe)")
                except Exception as e:
                    conn.rollback()
                    print(f"✗ supabase: export {name} fallito — {e}")
                    ok = False
    except Exception as e:
        print(f"✗ supabase: connessione fallita — {e}")
        return False
    return ok


def main() -> int:
    args = set(sys.argv[1:])
    do_q = not args or "--qdrant" in args
    do_db = not args or "--db" in args
    ok = True
    if do_q:
        ok = snapshot_qdrant() and ok
    if do_db:
        ok = export_supabase() and ok
    print("Backup completato." if ok else "Backup completato CON ERRORI (vedi sopra).")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
