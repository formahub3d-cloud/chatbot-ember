#!/usr/bin/env python3
"""verify_ingest.py — collaudo post-ingest del cervello su Qdrant.

Controlla che i payload contengano i tre livelli di permesso (org/tenant/sub_tenant)
introdotti dalla mappatura OVYON, e riporta la distribuzione per org e per tenant.
Utile subito dopo `POST /ingest` (re-ingest additiva) per confermare che lo scope è
sceso correttamente nel payload.

Uso (dalla radice del repo, con .env configurato):
    python scripts/verify_ingest.py [--sample N]

Opzionale: se GRANTS_BACKEND=supabase e DATABASE_URL sono impostati, esegue anche
una sanity-check della RLS contando i documenti visibili a un grant di esempio.

Exit code: 0 = tutti i payload ok; 1 = trovati payload senza i tre livelli.
"""
import argparse
import os
import sys
from collections import Counter

# Consente `python scripts/verify_ingest.py` dalla radice del repo.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings          # noqa: E402
from app.ingest import client, check_payload  # noqa: E402


def _scroll(sample: int):
    c = client()
    got, offset = [], None
    while len(got) < sample:
        points, offset = c.scroll(
            collection_name=settings.qdrant_collection,
            limit=min(256, sample - len(got)),
            offset=offset, with_payload=True,
        )
        got.extend(points)
        if offset is None or not points:
            break
    return got


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=1000,
                    help="numero massimo di punti da controllare (default 1000)")
    args = ap.parse_args()

    print(f"Qdrant: {settings.qdrant_url} · collection: {settings.qdrant_collection}")
    try:
        points = _scroll(args.sample)
    except Exception as e:  # noqa: BLE001 - errore di connessione/config
        print(f"⚠️  Qdrant non raggiungibile: {e}")
        print("   Controlla QDRANT_URL / QDRANT_API_KEY nel .env.")
        return 2
    if not points:
        print("⚠️  Nessun punto trovato: eseguire prima POST /ingest.")
        return 1

    by_org, by_tenant, bad = Counter(), Counter(), []
    for p in points:
        pl = p.payload or {}
        missing = check_payload(pl)
        if missing:
            bad.append((pl.get("slug", "?"), missing))
        by_org[pl.get("org")] += 1
        by_tenant[pl.get("tenant", pl.get("scope"))] += 1

    print(f"\nControllati {len(points)} chunk.")
    print("\nDistribuzione per org:")
    for org, n in by_org.most_common():
        print(f"  {str(org):12s} {n:5d}")
    print("\nDistribuzione per tenant:")
    for t, n in by_tenant.most_common():
        print(f"  {str(t):16s} {n:5d}")

    # Sanity-check RLS opzionale (solo se il backend Supabase è configurato).
    if settings.grants_backend.strip().lower() == "supabase" and settings.database_url.strip():
        try:
            from app import rls
            sample_grants = {"allowed_tenants": [next(iter(by_tenant))]}
            n_docs = rls.count_documents(sample_grants)
            print(f"\nRLS Supabase: {n_docs} documenti visibili a {sample_grants} "
                  f"(0 è normale se la tabella `documents` non è ancora popolata).")
        except Exception as e:  # noqa: BLE001 - informativo, non blocca
            print(f"\nRLS Supabase: check non eseguito ({e}).")

    if bad:
        print(f"\n❌ {len(bad)} chunk SENZA i tre livelli (mostro i primi 10):")
        for slug, miss in bad[:10]:
            print(f"  {slug}: mancano {miss}")
        print("\nRe-esegui l'ingest con la versione aggiornata di ingest.segments_for.")
        return 1

    print("\n✅ Tutti i chunk hanno org/tenant/sub_tenant (scope == tenant).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
