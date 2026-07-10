# Ricognizione — Fase 0 del progetto "OVY Orchestrator"

> Report tecnico preliminare (2026-07-08) per il potenziamento del sistema Cervello OVY
> + Ember verso: orchestratore multi-agente, skill library, auto-miglioramento continuo,
> generazione documenti, connettori clienti. **Nessun codice applicativo è stato scritto.**
> Da leggere e approvare prima della Fase 1 (schema dati).

## 1. Stack reale trovato

### chatbot-ember (motore, IN PRODUZIONE — clienti attivi)
- **Linguaggio/framework**: Python 3 · FastAPI · uvicorn. Deploy: **Railway**, auto-deploy
  a ogni push su `main` (Procfile). CI GitHub Actions: byte-compile + pytest (**208 test**).
- **LLM**: `app/providers.py` — switch Mistral/Claude da env (`LLM_PROVIDER`);
  **embeddings SEMPRE Mistral** (regola di repo). Nessuna logica provider fuori da providers.py.
- **RAG**: `app/rag.py` — Qdrant (cloud UE), filtro **server-side** per scope; pool candidati
  + soglia rilevanza + diversità MMR; risposta vincolata al contenuto con "non lo so".
- **Multi-tenant**: `app/tenants.py` — chiave → grant a 3 livelli (org / tenant / sub_tenant),
  4 backend (static json, Mongo, **Supabase `api_keys`** live, master key). Chiavi **hashate sha256**.
  Quote per tenant giornaliera + mensile (`key_usage`, contatore atomico per periodo).
- **Supabase**: accesso via **psycopg2 diretto** (shared pooler UE, retry anti-freddo);
  RLS applicata con GUC di sessione `ovyon.*` (`app/rls.py` → `session_grants`).
- **Osservabilità**: request-id, /ready, /metrics Prometheus, /admin/* (analytics, insights,
  learning, events, usage, access-logs, status), Sentry opzionale, alert costo per tenant.
- **Env var chiave**: MISTRAL_API_KEY, QDRANT_URL/API_KEY/COLLECTION, DATABASE_URL,
  GRANTS_BACKEND, ADMIN_TOKEN, CONTENT_ENC_KEY, ANALYTICS_PERSIST, REDIS_URL, ELEVENLABS_*.

### ovy-cervello (vault + front-end, Cloudflare Pages)
- Vault Obsidian (84 note indicizzate) = **fonte di verità** dei contenuti; lo scope nasce
  dal path (`forma/clienti/<x>/` → tenant `<x>`).
- Generatori Python (`build_all.py`): llms.txt, canvas, bookmarks, cervello-vivo,
  `note-index.json`, quality gate (7 regole). Il **pannello** (`/pannello`) è una PWA statica
  che parla con Ember via fetch (chiavi in localStorage, mai in pagina).
- Auto-miglioramento già esistente (embrione): gap/👎 → `/admin/learning` → `learning_to_bozze.py`
  → bozze in `_bozze/` → revisione umana → ingest.

### Schema Supabase attuale (da `db/ovyon_schema.sql`, schema OVYON)
- `organizations` / `tenants` / `sub_tenants` — anagrafica 3 livelli (code testuali = scope Qdrant).
- `documents` — metadati nota + `content_encrypted` (Fernet); code denormalizzati per RLS veloce.
- `access_logs` — audit trail (RLS: insert in sessione, read solo master).
- `analytics_events` — chat/gap/feedback persistiti (domanda REDATTA a monte).
- `key_usage` — quota per (key_hash, period).
- `api_keys` — ponte Ember: hash, grant 3 livelli, origins, branding jsonb.
- RLS: funzioni `ovyon.grants()/is_master()/can_read()` sui GUC di sessione; `'*'` = master.
- ⚠️ Limite ricognizione: ho letto il **DDL versionato**, non il DB live (nessuna credenziale
  in questa sessione) — eventuali derive schema live↔repo vanno verificate col primo accesso.

## 2. Punti di estensione naturali (dove l'orchestrator si aggancia SENZA toccare Ember)

1. **Stesso Supabase, tabelle nuove**: lo schema OVYON è già multi-tenant con RLS a funzioni
   riusabili (`ovyon.can_read`); le nuove tabelle (Fase 1) possono citare `tenant_id` uuid
   FK a `tenants` + code denormalizzato, e riusare le stesse policy-pattern.
2. **API Ember già pronte per l'orchestrator** (nessuna modifica richiesta):
   `/search` `/document` `/context` (lettura RAG con chiave tenant), `/writeback` (bozza con
   conferma), `/ingest` (re-index), `/admin/learning` (i gap da cui parte l'auto-miglioramento).
3. **Il pannello** è statico e facilmente estendibile: nuova vista "Orchestrator" = fetch verso
   il nuovo servizio (CORS da configurare sul servizio nuovo, non su Ember).
4. **Il ciclo bozze→conferma umana** esiste già ed è il precedente perfetto per la regola
   "le contraddizioni non si risolvono mai in automatico".

## 3. Rischi identificati

| # | Rischio | Mitigazione proposta |
|---|---|---|
| R1 | **Toccare Ember in produzione** (clienti attivi) | Repo/servizio separato `ovy-orchestrator`; comunica via API Ember + Supabase; zero modifiche al codice Ember in Fase 1-2 |
| R2 | **RLS incoerente sulle nuove tabelle** → leak cross-tenant | Ogni nuova tabella replica il pattern `ovyon.can_read` + test d'isolamento come `test_isolation.py` |
| R3 | **Ruolo DB troppo largo per il nuovo servizio** | Creare un ruolo Postgres dedicato all'orchestrator con GRANT solo sulle sue tabelle (non su `api_keys`) |
| R4 | **Costi ricerca web + LLM in loop schedulato** | Budget per run (max N gap/notte), quota per tenant, riuso alert costi esistente |
| R5 | **Contenuto web non verificato che inquina il cervello** | Pipeline scrive SOLO in `raw_sources`/`wiki_nodes` stato bozza; mai direttamente nel vault/Qdrant; contraddizioni in coda umana |
| R6 | **Credenziali connettori clienti** (Fase 5) | Mai in chiaro in tabella: `credenziali_ref` → secret manager (Railway env per-connettore o Supabase Vault) |
| R7 | **Drift schema DDL repo ↔ DB live** | Prima azione di Fase 1: `pg_dump --schema-only` di verifica (serve credenziale) |

## 4. Cosa NON va toccato senza permesso esplicito

- Il codice di `chatbot-ember` in produzione (in particolare: `tenants.py`, `rag.py`,
  `rls.py`, `main.py`) — l'orchestrator NON vive qui dentro.
- Le tabelle esistenti (`api_keys`, `documents`, `access_logs`, …): niente ALTER;
  solo tabelle NUOVE additive.
- Il flusso di conferma umana (write-back, contraddizioni): mai bypassato.
- Il branch `main` dei due repo: l'orchestrator nasce su repo dedicato; qualsiasi
  modifica futura a Ember passa da branch + approvazione.
- La regola embeddings=Mistral e il filtro scope server-side su Qdrant.

## 5. Proposta di priorità (da confermare)

**Fase 1 (schema) → Fase 2.1-2.2 (router + Ricercatore/Ingest/Cross-referencer) → Fase 3
(cron auto-miglioramento sui gap: È il valore più immediato, chiude il ciclo già iniziato)
→ Fase 2.5 (endpoint pannello + vista Orchestrator) → Fase 4 (documenti) → Fase 2.3 (agenti
di dominio) → Fase 5 (connettori, solo design).**
Razionale: i gap sono già tracciati e il ciclo bozze esiste — l'auto-miglioramento schedulato
è il primo pezzo che produce valore visibile senza dipendere dagli agenti di dominio.

## 6. Domande aperte (bloccanti per la Fase 1)

1. **API di ricerca**: propongo **Tavily** (nato per RAG/agenti, risposte già pulite,
   free tier 1.000 ricerche/mese, ~$0.008/ricerca poi) + eventualmente Firecrawl SOLO
   quando serviranno i connettori/scraping siti clienti (Fase 5). Confermi Tavily?
2. **Repo `ovy-orchestrator`**: non posso crearlo da questa sessione (scope limitato ai 2
   repo esistenti) → lo crei tu vuoto su GitHub e me lo aggiungi alla sessione, o preferisci
   che l'orchestrator nasca come cartella `orchestrator/` in un monorepo? (consiglio: repo separato)
3. **Accesso DB del nuovo servizio**: ruolo Postgres dedicato con grant solo sulle nuove
   tabelle (R3) — ok? Lo crei tu da SQL che ti preparo io.
4. **Scheduler Fase 3**: propongo **GitHub Actions schedule** (pattern già usato per
   reingest.yml, gratis, log visibili) invece di Railway cron o pg_cron. Confermi?
5. **LLM dell'orchestrator**: stesso stack (Mistral small per classificazione/ingest,
   Claude opzionale per generazione documenti di qualità)? Impatta i costi per run.
6. **Agenti di dominio** (Fase 2.3): per FORMA i vincoli sono chiari (anonimizzare, range
   di prezzo, fonti verificate). Per OVYON/HRH/ATS servono da te: scopo dell'agente,
   tono, cosa può/non può dire — anche solo 3 righe ciascuno.
7. **`wiki_nodes` vs vault**: i nodi wiki vivono SOLO su Supabase (per-tenant, RLS) e il
   vault resta la fonte del tenant FORMA, con promozione manuale bozza→nota? (mia
   raccomandazione, coerente con "il vault è la fonte di verità") — o vuoi sync bidirezionale?

---
*Fase 0 completata. In attesa di: approvazione report + risposte alle 7 domande → Fase 1 (proposta DDL, non applicata).*
