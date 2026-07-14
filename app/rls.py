"""Difesa in profondità lato database (Opzione 1, Sezione 9 del doc OVYON).

Imposta i grant del richiedente come **GUC di sessione** `ovyon.*`, così la RLS di
Supabase (`db/ovyon_schema.sql`) filtra automaticamente le tabelle protette
(`documents`, `access_logs`) quando Divina le interroga con un ruolo non privilegiato.

Uso tipico::

    from app import rls
    with rls.session_grants(grants) as (conn, cur):
        cur.execute("SELECT slug, title FROM documents")   # già filtrato dalla RLS
        rows = cur.fetchall()

I GUC si impostano con `set_config(name, value, is_local=true)`: è l'equivalente
parametrico (SQL-injection-safe) di `SET LOCAL`, valido per la sola transazione.
"""
from contextlib import contextmanager

from . import tenants
from .rag import _grant_lists

# Nomi dei GUC letti dalle funzioni RLS in db/ovyon_schema.sql (ovyon.grants()).
GUC = {
    "allowed_orgs": "ovyon.allowed_orgs",
    "allowed_tenants": "ovyon.allowed_tenants",
    "allowed_sub_tenants": "ovyon.allowed_sub_tenants",
}


def guc_values(grants) -> dict:
    """Mappa i grant (lista storica o dict) nei valori GUC (liste separate da virgola,
    coerenti con string_to_array(current_setting(...), ',') lato SQL)."""
    orgs, tenants_, subs = _grant_lists(grants)
    return {
        GUC["allowed_orgs"]: ",".join(orgs),
        GUC["allowed_tenants"]: ",".join(tenants_),
        GUC["allowed_sub_tenants"]: ",".join(subs),
    }


def set_grants(cur, grants) -> None:
    """Emette i SET LOCAL (via set_config) per la transazione corrente."""
    for name, val in guc_values(grants).items():
        cur.execute("SELECT set_config(%s, %s, %s)", (name, val, True))


@contextmanager
def session_grants(grants):
    """Context manager: apre una connessione, applica i grant come GUC di sessione
    e la chiude. Da usare per ogni lettura/scrittura sulle tabelle sotto RLS."""
    conn = tenants._conn()
    try:
        cur = conn.cursor()
        set_grants(cur, grants)
        yield conn, cur
        conn.commit()
    finally:
        conn.close()


def count_documents(grants) -> int:
    """Conta i documenti VISIBILI ai grant (utile come sanity-check della RLS).
    Se `documents` è vuota o la RLS nasconde tutto, ritorna 0."""
    with session_grants(grants) as (_conn_, cur):
        cur.execute("SELECT count(*) FROM documents")
        return int(cur.fetchone()[0])
