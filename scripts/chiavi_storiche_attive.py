#!/usr/bin/env python3
"""Quali delle chiavi del Postgres storico sono ANCORA attive? (05-08-2026)

Contesto: nel Postgres allegato a Railway c'è la tabella `tenants` nella forma
storica, con la colonna `key` in CHIARO — quattro chiavi rimaste lì senza
rotazione per mesi. Prima di spegnere quel servizio (S1.6) va deciso cosa
farne, e la decisione dipende da un dato che nessuno ha ancora guardato:
**quali di quelle chiavi risultano ancora valide oggi.**

Come si risponde senza toccare le chiavi in chiaro: `api_keys.key_hash` è lo
sha256 della chiave, e l'inventario prodotto da `snapshot_postgres_legacy.sh`
contiene esattamente quegli sha256. Si confrontano gli hash — le chiavi in
chiaro non servono e non entrano mai in questo script.

Uso:
    export DATABASE_URL='postgresql://…'      # Supabase (NON il Postgres storico)
    python3 scripts/chiavi_storiche_attive.py postgres-legacy-inventario.md

Esito: un elenco diviso in due, ATTIVE e INATTIVE, che è quello che serve per
applicare la decisione del titolare (05-08):
  · INATTIVE → si ruotano subito (`scripts/reset_chiavi.py`): non c'è nessuno
    da disturbare, e una chiave inattiva ma nota è un rischio senza contropartita.
  · ATTIVE   → NON si toccano. Si scrive un piano di rotazione nel
    diario-problemi e decide il titolare, perché revocarle si vede dal cliente.

Come tutti gli script di manutenzione di questo repo: `urllib`/stdlib, nessuna
dipendenza, gira col Python di sistema senza venv.
"""
import os
import re
import sys


def hash_dall_inventario(percorso: str) -> dict[str, str]:
    """Legge gli sha256 dalla tabella markdown dell'inventario.

    Il formato lo produce `snapshot_postgres_legacy.sh`:
        | `<sha256>` | <name> | `<allowed_scopes>` |
    Si accetta solo un hash esadecimale di 64 caratteri: se il file è un altro,
    meglio non trovare niente che trovare qualcosa per sbaglio.
    """
    trovati: dict[str, str] = {}
    riga_hash = re.compile(r"^\|\s*`([0-9a-f]{64})`\s*\|\s*([^|]*)\|")
    with open(percorso, encoding="utf-8") as f:
        for riga in f:
            m = riga_hash.match(riga.strip())
            if m:
                trovati[m.group(1)] = m.group(2).strip() or "(senza nome)"
    return trovati


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    inventario = sys.argv[1]
    dsn = os.environ.get("DATABASE_URL", "").strip()
    if not dsn:
        print("ERRORE: esporta DATABASE_URL con la DSN di SUPABASE.", file=sys.stderr)
        return 1

    chiavi = hash_dall_inventario(inventario)
    if not chiavi:
        print(f"ERRORE: nessun hash trovato in {inventario}. "
              "È l'inventario prodotto da snapshot_postgres_legacy.sh?", file=sys.stderr)
        return 1

    import psycopg2   # import locale: lo script gira solo dove serve

    attive, inattive = [], []
    with psycopg2.connect(dsn, connect_timeout=10) as conn:
        with conn.cursor() as cur:
            for kh, nome in chiavi.items():
                cur.execute(
                    "SELECT name, active, allowed_tenants FROM api_keys WHERE key_hash = %s",
                    (kh,),
                )
                riga = cur.fetchone()
                if riga and riga[1]:
                    attive.append((kh, nome, riga[0], list(riga[2] or [])))
                else:
                    # Non presente in api_keys, oppure presente ma revocata:
                    # in entrambi i casi non è una chiave che qualcuno sta usando.
                    inattive.append((kh, nome, "revocata" if riga else "non presente"))

    print(f"Chiavi nell'inventario: {len(chiavi)}\n")

    print(f"── ATTIVE ({len(attive)}) — NON toccarle, serve la decisione del titolare")
    for kh, nome_storico, nome_oggi, scope in attive:
        print(f"   {kh[:16]}…  storico: {nome_storico}  ·  oggi: {nome_oggi}  ·  scope: {scope}")
    if not attive:
        print("   (nessuna)")

    print(f"\n── INATTIVE ({len(inattive)}) — si ruotano subito con reset_chiavi.py")
    for kh, nome_storico, perche in inattive:
        print(f"   {kh[:16]}…  storico: {nome_storico}  ·  {perche}")
    if not inattive:
        print("   (nessuna)")

    if attive:
        print("\nProssimo passo: il piano di rotazione delle ATTIVE è in "
              "docs/diario-problemi.md — lo approva il titolare, non lo script.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
