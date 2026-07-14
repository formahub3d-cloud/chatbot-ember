# OVYON — Schema Supabase / Postgres

Layer dati a tre livelli del cervello OVY (Sezione 4.1 del doc di architettura),
con **RLS multi-livello** (Sezione 9). Corrisponde all'**Opzione 1** della nota
`ovyon/docs/doc-ovyon-ember-scope`: **Supabase come layer identità / permessi /
audit; Qdrant resta il vector store**.

## File

| File | Contenuto |
|---|---|
| `ovyon_schema.sql` | tabelle ER, indici, trigger, funzioni helper e policy RLS |
| `seed.example.sql` | esempio di seed (org/tenant/chiavi) — **non** con chiavi reali |

## Applicare

```bash
psql "$DATABASE_URL" -f db/ovyon_schema.sql
psql "$DATABASE_URL" -f db/seed.example.sql   # opzionale, per un ambiente di prova
```

Su Supabase: incolla `ovyon_schema.sql` nel SQL editor ed esegui.

## Modello

- `organizations > tenants > sub_tenants > documents` (1:N a ogni livello).
- Ogni riga di `documents` porta i **code denormalizzati** `org_code/tenant_code/
  sub_code`: coincidono con lo `scope`/segmento di Divina (`ingest.segments_for`),
  così i permessi combaciano senza traduzioni.
- `api_keys`: chiavi-tenant **hashate** (mai in chiaro) con i grant a tre livelli
  (`allowed_orgs/allowed_tenants/allowed_sub_tenants`, code testuali; `*` = master)
  — è l'equivalente Postgres di `tenants.json`/Mongo già usati da Divina.
- `access_logs`: audit trail append-only (Sezione 9).

## Come la RLS ottiene lo scope

Le policy leggono i grant del richiedente da **GUC di sessione** `ovyon.*`, che il
backend imposta per-transazione prima di interrogare:

```sql
BEGIN;
SET LOCAL ovyon.allowed_orgs        = 'forma';
SET LOCAL ovyon.allowed_tenants     = 'ats,forma-core';
SET LOCAL ovyon.allowed_sub_tenants = '';
SELECT slug, title FROM documents;   -- vede solo le righe consentite
COMMIT;
```

`ovyon.can_read(org, tenant, sub)` applica l'OR tra i livelli (un grant su `org`
copre i suoi tenant); `'*'` in un qualunque array = master.

> Il `service_role` di Supabase **bypassa** la RLS: per l'isolamento effettivo,
> connettersi con un ruolo non privilegiato **oppure** impostare sempre i GUC
> `ovyon.*` per ogni richiesta tenant. Difesa in profondità: la RLS protegge i
> metadati/log, il filtro Qdrant (`rag.build_filter`) protegge il contenuto.

## Integrazione con Divina

Con `GRANTS_BACKEND=supabase` + `DATABASE_URL`:

- **Chiavi → grant**: `app/tenants.resolve_key_apikeys` legge `api_keys` per `key_hash`
  e restituisce i grant a tre livelli (usati da `main._grants` → `rag.build_filter`).
- **Audit**: `app/tenants.log_access` scrive `access_logs` a ogni `/search`·`/document`·
  `/writeback`, dentro una sessione con i GUC `ovyon.*` (`app/rls.session_grants`), così
  la policy RLS scope-checked è rispettata.
- **Documenti**: `app/docstore.sync_notes` (chiamato da `ingest.run`) fa **upsert dei
  metadati** delle note in `documents` (org/tenant/sub + slug/title/path/tags), creando
  al volo le righe `organizations/tenants/sub_tenants` mancanti. Il corpo resta su Qdrant;
  `content_encrypted` è per la fase compliance. Così la RLS a livello di documento è reale.

Nessun cambio allo schema Qdrant: Supabase è il layer identità/permessi/audit/metadati.
