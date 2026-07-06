"""Onboarding cliente sul backend Supabase (tabella api_keys dello schema OVYON):
emissione chiave-tenant, elenco, revoca e branding (white-label).

La chiave IN CHIARO viene mostrata UNA SOLA VOLTA alla creazione: nel DB si salva
solo l'hash (sha256). Se la perdi, si revoca e si riemette — non si recupera.

Uso (con DATABASE_URL + GRANTS_BACKEND=supabase; es. su Railway: `railway run …`):
  python -m app.manage_apikeys add "Cliente X" --orgs forma --tenants clientex \
        --origins https://www.clientex.it --quota 2000
  python -m app.manage_apikeys brand "Cliente X" --title "Assistente X" --accent "#0ED4E4" \
        --subtitle "Assistente AI" --avatar https://cdn/x.png --greeting "Ciao!"
  python -m app.manage_apikeys list
  python -m app.manage_apikeys revoke "Cliente X"
"""
import argparse
import json
import sys

from .config import settings
from .security import hash_key, new_key
from . import tenants as T


def _jsonb(branding):
    """Serializza il branding per una colonna jsonb (via cast %s::jsonb); None → NULL."""
    return json.dumps(branding) if branding else None


def _ready() -> None:
    if not (settings.grants_backend.strip().lower() == "supabase" and settings.database_url.strip()):
        raise SystemExit("Backend Supabase non attivo: imposta GRANTS_BACKEND=supabase e DATABASE_URL.")


def _arr(s) -> list[str]:
    if isinstance(s, (list, tuple)):
        return [str(x).strip() for x in s if str(x).strip()]
    return [x.strip() for x in (s or "").split(",") if x.strip()]


_INSERT = (
    "INSERT INTO api_keys (key_hash, name, active, quota_day, allowed_orgs, "
    "allowed_tenants, allowed_sub_tenants, allowed_origins, branding) "
    "VALUES (%s,%s,true,%s,%s,%s,%s,%s,%s::jsonb) ON CONFLICT (key_hash) DO NOTHING"
)


def create_key(name, orgs=None, tenants_=None, subs=None, origins=None, quota=0, branding=None) -> str:
    """Crea una chiave-tenant e la inserisce in api_keys. Ritorna la chiave in CHIARO
    (da consegnare al cliente e non più recuperabile)."""
    key = new_key("ovy")
    with T._conn() as c:
        with c.cursor() as cur:
            cur.execute(_INSERT, (
                hash_key(key), name, int(quota or 0), _arr(orgs), _arr(tenants_),
                _arr(subs), _arr(origins), _jsonb(branding),
            ))
        c.commit()
    return key


def set_branding(name, branding: dict) -> int:
    """Imposta/aggiorna il branding (white-label) di un tenant per nome. Righe toccate."""
    with T._conn() as c:
        with c.cursor() as cur:
            cur.execute("UPDATE api_keys SET branding=%s::jsonb WHERE name=%s",
                        (_jsonb(branding), name))
            n = cur.rowcount
        c.commit()
    return n


def revoke(name) -> int:
    """Disattiva (active=false) le chiavi con questo nome. Non le cancella."""
    with T._conn() as c:
        with c.cursor() as cur:
            cur.execute("UPDATE api_keys SET active=false WHERE name=%s", (name,))
            n = cur.rowcount
        c.commit()
    return n


def list_keys() -> list[dict]:
    with T._conn() as c:
        with c.cursor() as cur:
            cur.execute("SELECT name, active, allowed_orgs, allowed_tenants, quota_day, "
                        "(branding IS NOT NULL) FROM api_keys ORDER BY name")
            rows = cur.fetchall()
    return [{"name": r[0], "active": r[1], "orgs": r[2], "tenants": r[3],
             "quota_day": r[4], "branding": r[5]} for r in rows]


# ── CLI ──────────────────────────────────────────────────────────────────────

def _branding_from_args(a) -> dict:
    b = {}
    for k in ("title", "subtitle", "accent", "avatar", "logo", "greeting"):
        v = getattr(a, k, None)
        if v:
            b[k] = v
    return b


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="manage_apikeys", description="Onboarding chiavi-tenant su Supabase (api_keys).")
    sub = p.add_subparsers(dest="cmd", required=True)

    pa = sub.add_parser("add", help="crea una chiave e stampa la chiave in chiaro (una volta)")
    pa.add_argument("name")
    pa.add_argument("--orgs", default=""); pa.add_argument("--tenants", default="")
    pa.add_argument("--subs", default=""); pa.add_argument("--origins", default="")
    pa.add_argument("--quota", type=int, default=0)
    for k in ("title", "subtitle", "accent", "avatar", "logo", "greeting"):
        pa.add_argument("--" + k, default=None)

    pb = sub.add_parser("brand", help="imposta il branding (white-label) di un tenant")
    pb.add_argument("name")
    for k in ("title", "subtitle", "accent", "avatar", "logo", "greeting"):
        pb.add_argument("--" + k, default=None)

    pr = sub.add_parser("revoke", help="disattiva le chiavi con questo nome"); pr.add_argument("name")
    sub.add_parser("list", help="elenca le chiavi (senza segreti)")

    a = p.parse_args(argv)
    _ready()
    if a.cmd == "add":
        key = create_key(a.name, a.orgs, a.tenants, a.subs, a.origins, a.quota, _branding_from_args(a) or None)
        print("Chiave creata per '%s'. Consegnala al cliente e NON perderla (mostrata una volta):\n\n  %s\n" % (a.name, key))
    elif a.cmd == "brand":
        n = set_branding(a.name, _branding_from_args(a))
        print(f"Branding aggiornato su {n} chiave/i con nome '{a.name}'.")
    elif a.cmd == "revoke":
        print(f"Revocate {revoke(a.name)} chiave/i con nome '{a.name}'.")
    elif a.cmd == "list":
        for r in list_keys():
            flag = "attiva " if r["active"] else "REVOCATA"
            print(f"- {r['name']:<24} [{flag}] tenants={r['tenants']} quota/d={r['quota_day']} brand={'sì' if r['branding'] else 'no'}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
