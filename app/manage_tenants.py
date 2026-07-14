"""Gestione tenant su MongoDB — chiavi hashate, quote, revoca.

La chiave in chiaro viene mostrata UNA SOLA VOLTA alla creazione: nel DB si salva
solo l'hash. Se la perdi, si rigenera (rotate), non si recupera.

Uso (in cloud con MONGO_URI impostata, es. su Railway):
  railway run python -m app.manage_tenants seed
  railway run python -m app.manage_tenants add "Cliente X" scopeX --origins https://www.clientex.it --quota 2000 --accent "#0ED4E4"
  railway run python -m app.manage_tenants list
  railway run python -m app.manage_tenants revoke <name|key_hash>
  railway run python -m app.manage_tenants rotate <name|key_hash>
"""
import argparse
import sys

from .config import settings
from .security import hash_key, new_key
from . import tenants as T


def _col():
    if not settings.mongo_uri.strip():
        raise SystemExit("MONGO_URI non impostata: configura MongoDB per usare questa CLI.")
    return T._mdb()[settings.tenants_collection]


def cmd_seed(_args):
    n = T.mongo_seed()
    print(f"Seed OK: {n} tenant importati dalla sorgente statica (chiavi hashate).")


def cmd_add(args):
    col = _col()
    col.create_index("key_hash", unique=True)
    key = new_key()
    doc = {
        "key_hash": hash_key(key),
        "name": args.name,
        "allowed_scopes": [s.strip() for s in args.scopes.split(",") if s.strip()],
        "allowed_origins": [o.strip() for o in (args.origins or "").split(",") if o.strip()],
        "branding": {"title": args.title or args.name, "accent": args.accent} if args.accent or args.title else {},
        "quota_day": int(args.quota),
        "active": True,
    }
    col.insert_one(doc)
    print("Tenant creato. CHIAVE (mostrata una sola volta, salvala ora):\n")
    print(f"    {key}\n")
    print(f"  nome: {doc['name']} · scope: {doc['allowed_scopes']} · quota/giorno: {doc['quota_day']}")


def cmd_list(_args):
    for d in _col().find({}, {"name": 1, "key_hash": 1, "allowed_scopes": 1, "quota_day": 1, "active": 1}):
        state = "attivo" if d.get("active", True) else "REVOCATO"
        print(f"- {d.get('name','?'):28} [{state}] scope={d.get('allowed_scopes')} "
              f"quota={d.get('quota_day',0)} hash={d.get('key_hash','')[:12]}…")


def _match(col, ident):
    return col.find_one({"$or": [{"name": ident}, {"key_hash": ident}]})


def cmd_revoke(args):
    col = _col()
    r = col.update_one({"$or": [{"name": args.ident}, {"key_hash": args.ident}]}, {"$set": {"active": False}})
    print("Revocato." if r.modified_count else "Nessun tenant corrispondente.")


def cmd_rotate(args):
    col = _col()
    d = _match(col, args.ident)
    if not d:
        print("Nessun tenant corrispondente."); return
    key = new_key()
    col.update_one({"_id": d["_id"]}, {"$set": {"key_hash": hash_key(key), "active": True}})
    print(f"Nuova CHIAVE per '{d.get('name')}' (salvala ora):\n\n    {key}\n")


def main(argv=None):
    p = argparse.ArgumentParser(prog="manage_tenants", description="Gestione tenant Divina su MongoDB")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("seed").set_defaults(func=cmd_seed)
    a = sub.add_parser("add"); a.set_defaults(func=cmd_add)
    a.add_argument("name"); a.add_argument("scopes", help="scope separati da virgola")
    a.add_argument("--origins", default=""); a.add_argument("--quota", default=0)
    a.add_argument("--accent", default=""); a.add_argument("--title", default="")
    sub.add_parser("list").set_defaults(func=cmd_list)
    rv = sub.add_parser("revoke"); rv.set_defaults(func=cmd_revoke); rv.add_argument("ident")
    ro = sub.add_parser("rotate"); ro.set_defaults(func=cmd_rotate); ro.add_argument("ident")
    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    sys.exit(main())
