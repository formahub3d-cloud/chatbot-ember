#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# S1.4 · Snapshot del Postgres STORICO di Railway, prima di spegnerlo (S1.6).
# ═══════════════════════════════════════════════════════════════════════════
# Cosa c'è dentro quel database (verificato in dashboard il 05-08-2026):
#   una sola tabella, `tenants`, 4 righe, ~16 KB. È il fossile del tenant store
#   di quando DATABASE_URL puntava lì (la creava app/tenants.py::ensure_seeded,
#   che da oggi non la crea più).
#
# ⚠️  QUELLA TABELLA CONTIENE LE CHIAVI-TENANT IN CHIARO.
#     La colonna `key` è la chiave vera, non il suo hash: è la forma storica,
#     precedente ad `api_keys` (dove le chiavi vivono hashate). Quindi il dump
#     completo è un SEGRETO e non entra nel repo — regola tassativa n.1.
#
# Per questo lo script produce DUE file, e uno solo dei due si committa:
#   · postgres-legacy-snapshot.sql   dump completo — GITIGNORATO, da custodire
#                                    fuori dal repo (password manager / storage
#                                    cifrato), è l'unica copia di quei dati.
#   · postgres-legacy-inventario.md  la PROVA committabile: tabelle, conteggi,
#                                    colonne, e le chiavi ridotte al loro
#                                    sha256. Serve a dimostrare che lo snapshot
#                                    è stato fatto e cosa conteneva, senza
#                                    pubblicare niente di segreto.
#
# Uso (serve la Railway CLI autenticata, o una DSN già in mano):
#   railway link                 # progetto Divina
#   railway variables -s Postgres | grep DATABASE_URL      # oppure:
#   DATABASE_URL='postgresql://…' ./scripts/snapshot_postgres_legacy.sh
#
# Verifica: lo script confronta il conteggio righe letto dal database con
# quello ritrovato nel dump. Se non combaciano si ferma con un errore — uno
# snapshot che non si sa se è completo non è uno snapshot.
# ═══════════════════════════════════════════════════════════════════════════
set -euo pipefail

DSN="${DATABASE_URL:-}"
if [[ -z "$DSN" ]]; then
  echo "ERRORE: esporta DATABASE_URL con la DSN del Postgres STORICO." >&2
  echo "        (non quella di Supabase: qui si fotografa il servizio da spegnere)" >&2
  exit 1
fi

DUMP="postgres-legacy-snapshot.sql"
INVENTARIO="postgres-legacy-inventario.md"

echo "→ inventario delle tabelle…"
TABELLE=$(psql "$DSN" -At -c "
  select table_name from information_schema.tables
  where table_schema='public' order by table_name")

if [[ -z "$TABELLE" ]]; then
  echo "ERRORE: nessuna tabella trovata. DSN sbagliata?" >&2
  exit 1
fi

echo "→ dump completo in $DUMP…"
pg_dump --no-owner --no-privileges --column-inserts "$DSN" > "$DUMP"

{
  echo "# S1.4 · Inventario del Postgres storico di Railway"
  echo
  echo "> Generato da \`scripts/snapshot_postgres_legacy.sh\` il $(date -u +%Y-%m-%dT%H:%M:%SZ)."
  echo "> Il dump completo (\`$DUMP\`) **non è in questo repo**: contiene le"
  echo "> chiavi-tenant in chiaro. Qui resta la prova di cosa c'era dentro."
  echo
  echo "| Tabella | Righe |"
  echo "|---|---|"
  TOTALE=0
  for t in $TABELLE; do
    n=$(psql "$DSN" -At -c "select count(*) from \"$t\"")
    TOTALE=$((TOTALE + n))
    echo "| \`$t\` | $n |"
  done
  echo
  echo "**Totale righe: $TOTALE**"
  echo

  if echo "$TABELLE" | grep -qx "tenants"; then
    echo "## \`tenants\` — forma storica, chiavi ridotte al loro hash"
    echo
    echo "| sha256(key) | name | allowed_scopes |"
    echo "|---|---|---|"
    psql "$DSN" -At -F '|' -c "
      select encode(digest(key,'sha256'),'hex'), coalesce(name,''), allowed_scopes::text
      from tenants order by name" 2>/dev/null \
      || psql "$DSN" -At -F '|' -c "
      select md5(key) || ' (md5: pgcrypto non disponibile)', coalesce(name,''), allowed_scopes::text
      from tenants order by name" \
      | while IFS='|' read -r h n s; do echo "| \`$h\` | $n | \`$s\` |"; done
    echo
    echo "> Le chiavi in chiaro sono **solo** nel dump fuori repo. In produzione"
    echo "> le chiavi vivono hashate nella tabella \`api_keys\` di Supabase:"
    echo "> questa tabella non è più la sorgente dal passaggio a TENANTS_JSON."
  fi
} > "$INVENTARIO"

echo "→ verifica di completezza…"
RIGHE_DB=$(psql "$DSN" -At -c "
  select coalesce(sum(n),0) from (
    select (xpath('/row/c/text()',
      query_to_xml(format('select count(*) as c from %I.%I', table_schema, table_name),
                   false, true, '')))[1]::text::int as n
    from information_schema.tables where table_schema='public'
  ) x")
RIGHE_DUMP=$(grep -c "^INSERT INTO" "$DUMP" || true)

echo "   righe nel database: $RIGHE_DB · INSERT nel dump: $RIGHE_DUMP"
if [[ "$RIGHE_DB" != "$RIGHE_DUMP" ]]; then
  echo "ERRORE: conteggi diversi — lo snapshot NON è verificato. Non spegnere niente." >&2
  exit 1
fi

echo
echo "✓ Snapshot verificato."
echo "  · $DUMP          → SPOSTALO FUORI DAL REPO (contiene chiavi in chiaro)"
echo "  · $INVENTARIO    → questo si committa"
echo
echo "Solo dopo aver messo al sicuro il dump si può procedere con S1.6"
echo "(cancellazione del servizio Postgres dalla dashboard Railway)."
