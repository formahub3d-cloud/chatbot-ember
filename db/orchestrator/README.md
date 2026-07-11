# DIVINA — Fase 1: schema dati (PROPOSTA)

> Stato: **in revisione — NON applicato**. Questi file sono la consegna della Fase 1
> del progetto OVY Orchestrator ("Divina"). Vivranno nel repo `ovy-orchestrator`
> appena esiste; nel frattempo sono versionati qui (solo file, zero impatto su Ember).

## File

| File | Cosa fa |
|---|---|
| `001_divina_schema.sql` | 8 tabelle nuove (raw_sources, wiki_nodes, node_links, contradictions, agents, skills, doc_templates, client_connectors) + RLS + seed agenti/skill/template |
| `002_divina_role.sql` | Ruolo Postgres `divina` a minimo privilegio (mai api_keys, niente DELETE, RLS attiva) |

Entrambi passano il parser PostgreSQL (pglast). Sono **additivi**: nessuna modifica
alle tabelle esistenti dello schema OVYON.

## Decisioni di design (dalle risposte dell'11/07)

1. **Stesso pattern RLS di Ember**: ogni tabella-dati porta `org_code`/`tenant_code`
   e usa `ovyon.can_read()` sui GUC di sessione → isolamento identico, testabile
   con gli stessi test di `test_isolation.py`.
2. **Regola ferrea Divina**: i campi `min_tier`/`archetype` esistono SOLO sulle
   tabelle di *capability* (skills, doc_templates, agents). Le tabelle di *contenuto*
   non hanno tier: il tier non amplia mai lo scope dei dati.
3. **Conferma umana strutturale**: `wiki_nodes.status` nasce `bozza`;
   `contradictions.resolved_by` è pensato per un nome umano — il ruolo `divina`
   non ha DELETE da nessuna parte e l'audit è append-only.
4. **wiki_nodes solo su Supabase** (Q7): il vault resta la fonte di verità FORMA;
   la promozione bozza→nota vault è manuale (`status='promosso'` traccia l'avvenuta).
5. **Gap letti via API** (`/admin/learning`), non dal DB: il ruolo non vede
   `analytics_events`.

## Come si applica (manuale, ~10 min — Andrea)

1. Rivedi i due file (in particolare i prompt del seed e i vincoli `constraints`).
2. Supabase → SQL editor → esegui `001` → poi l'UPDATE dei `tenant_id` indicato nel seed.
3. Genera una password forte → sostituiscila in `002` → esegui `002`.
4. Esegui le 4 **verifiche post-applicazione** in coda a `002` (api_keys negata,
   RLS isolata, delete negato, audit append-only) e conserva l'esito.
5. Metti `DIVINA_DATABASE_URL` da parte: servirà al servizio Divina (Fase 2).

## Prossimo passo (Fase 2 — dopo l'applicazione)

Servizio `ovy-orchestrator` separato su Railway: router intenti → agenti di sistema
(Ricercatore Tavily / Ingest / Cross-referencer / Manutentore) → skill library →
endpoint per il pannello (`/ingest/run`, `/contradictions`, `/nodes/recent`, `/docs/generate`).
