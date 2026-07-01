"""Inizializza la tabella `tenants` su Postgres e la popola dalla sorgente statica
(TENANTS_JSON in cloud, oppure tenants.json in locale).

Uso:
  railway run python -m app.seed_tenants     # in cloud (DATABASE_URL già presente)
  # oppure, in locale con DATABASE_URL esportata:
  python -m app.seed_tenants
"""
from .config import settings
from .tenants import load_static, init_and_seed

if __name__ == "__main__":
    if not settings.database_url.strip():
        raise SystemExit("DATABASE_URL non impostata: collega il Postgres al servizio.")
    seed = load_static()
    if not seed:
        raise SystemExit("Nessun tenant da seminare (TENANTS_JSON/tenants.json vuoti).")
    n = init_and_seed(seed)
    print(f"Seed OK: {n} tenant scritti nel database ({', '.join(seed)})")
