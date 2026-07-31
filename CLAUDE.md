# CLAUDE.md — Contesto progetto per Claude Code

> Leggi questo file prima di lavorare. Aggiornato al 31-07-2026 (era fermo di tre
> settimane: ora sa di orbite, voce e guardiano). Prodotto: **Divina** — dominio
> `divina.formahub.it`. Nomi storici («Ember», «Jarvis», «OVY») rimossi da ciò che
> una persona legge; restano SOLO dove sono contratti (vedi sotto).

## Cos'è

**Divina** è il prodotto AI di FORMA, due facce sotto lo stesso brand:
- **questo repo (`chatbot-ember`) = il motore**: chatbot RAG multi-tenant + il cervello (retrieval, ingest, admin, voce);
- **`ovy-orchestrator` = l'orchestratore**: i 3 companion (Dante/Virgilio/Beatrice), che parlano col motore SOLO via API.

La **console unica** (`/panel/`, servita da entrambi i servizi come copia byte-identica)
unisce le due facce. Il cervello è un vault Obsidian (repo `ovy-cervello`) di
Andrea Aloia / FORMA. FORMA lo usa internamente (tenant 0), **ATS** è il pilota,
poi si vende ai clienti. Regola d'oro: **un solo motore, molte chiavi** — ogni
cliente è un *tenant* con una chiave che limita le aree del cervello che legge.

> **Identificatori-contratto col vecchio nome — NON rinominarli** (li leggono
> clienti, database, segreti o il calcolo dei permessi): DB Mongo `MONGO_DB=ember`,
> prefisso chiavi tenant `ember_…`/`ovy_…` (già nei siti dei clienti), logger
> `ember`, segreti/variabili `EMBER_URL`/`EMBER_ADMIN_TOKEN` (CI + Railway, si
> cambiano solo in coppia), nomi tool MCP `ovy_*`, cartella `ovyon/` del vault
> (= scope: rinominarla fa SPARIRE le note ai tenant), schema/GUC SQL `ovyon.*`,
> alias `ember-*`/`jarvis-production-e680.up.railway.app`. Dettagli e piani di
> migrazione: prompt «Togliere Ember e OVY» del 31-07.

## Architettura

```
note .md del vault ──ingest──> Qdrant (vettori + scope/org/tenant/sub_tenant/links)
                                    │ retrieval filtrato per scope (+ focus orbita)
     domanda + chiave tenant ──────►│
                                    ▼
                       LLM (Mistral/Claude) ──> risposta + fonti (+ ⟦fuori⟧ solo owner)
upload ──OCR──► estrazione ──(conferma umana)──► write-back vault (marcato se da conversazione)
```

**Scope = permesso**, calcolato dal path: `forma/clienti/<X>/…` → `<X>`;
`forma/…` → `forma-core`; `andrea-aloia/…` → `andrea`; `ovyon/…` → `ovyon`.
Tre livelli additivi nel payload (org/tenant/sub_tenant); `rag.build_filter`
accetta grant come lista storica o dict per livello. Il **focus** (orbita scelta
in console) è un filtro slug in `must`: restringe soltanto, mai allarga.
**Owner** (`branding.owner=true`, server-side): conversazione libera con
provenienza obbligatoria ⟦fuori⟧…⟦/fuori⟧, resa come blocchi «fuori dal
cervello · non verificato»; i tenant clienti restano vincolati al vault.

## Mappa file

- `app/config.py` — settings da `.env` (incl. `VAULT_GIT_REF=main`, guardie ingest, espressività voce `ELEVENLABS_*`)
- `app/providers.py` — embeddings + chat (switch Mistral/Claude)
- `app/ingest.py` — vault→Qdrant: sync git deterministico (fetch+reset, clone-swap che preserva i dati cliente, MAI riuso silenzioso), guard anti-stantio (`INGEST_MAX_VAULT_AGE_H`), guard min-note, perimetro unico `is_note_included`, `vault_info()` (commit+data in /ingest e /admin/brain)
- `app/rag.py` — retrieval filtrato + risposta vincolata; focus_slugs (O2); free/owner con marcatori (O4); tier=solo stile; web additivo
- `app/voice.py` — proxy STT/TTS (chiavi SUL SERVER): ElevenLabs con `voice_settings` da env + `language_code`, TTS in streaming (0 byte → 502, mai un 200 muto), `status()` per /admin/status (`voice_id_set` = spia voce italiana)
- `widget/voce.js` — **MOTORE VOCALE UNICO** (U1): frasi (emSentenze, marcatori testati), coda TTS ordinata, barge-in con soglia RELATIVA all'eco (K appreso, marcatori EM_VAD testati, `setBarge` a caldo), invio automatico a fine parlato, parziali STT, ampiezza in/out per l'orb. Copia byte-identica in `panel/voce.js` (parità = test). La meccanica voce si tocca SOLO qui.
- `widget/embed.js` — widget embeddable (Shadow DOM); carica voce.js come fratello; fallback browser se il modulo manca
- `panel/index.html` — console SPA (file unico, no build; versione nel footer): home=cervello vivo (O1), «Lavora con Divina» con orbite CLIENTI/AREE/PROGETTI + lenti dai path (O2/O3), modo vocale a tutto schermo con orb «onda sonora» (U2) e trascritto che sfuma (U3), «Miglioramenti» (M1: unisce roadmap+task+proposte; IN CORSO=solo coda viva), «Salva nel cervello» con anteprima+conferma (O4), registro audit (M3), modalità cliente e demo
- `panel/brain3d.js` — renderer 3D del grafo (istanza, riusato da home e Cervello vivo)
- `app/main.py` — API: `/health` `/ingest` `/chat` (SSE; `focus`; free per owner) `/upload` `/voice/*`; MCP: `/search` `/document` `/context` `/writeback` (con `origin=conversazione` → marcatura server-side «NON verificato»); admin: `/admin/status` (spie voce), `/admin/brain*`, `/admin/tasks` (brain_tasks, kind incl. `audit`), `/admin/roadmap`, `/admin/proposals`, `/admin/clients*`, `/admin/learning`; `/client/*` (accessi cliente via `app/clientauth.py`)
- `app/tenants.py` `app/rls.py` `app/docstore.py` `app/brain.py` `app/braintasks.py` `app/proposals.py` — chiavi/RLS/metadati/grafo/coda/proposte
- `db/` — DDL Supabase: `schema.sql`, `brain_tasks*.sql`, `brain_graph.sql`, `client_access.sql` (i nomi SQL interni, es. schema `ovyon`, sono contratti e restano)
- `scripts/` — `test_console_headless.js` (**il guardiano**: in CI a ogni push), `test_voce_sentenze.js` (17 casi chunker), `test_voce_vad.js` (7 casi barge-in), `contract_console.py` (console↔API, 0 endpoint fantasma), `count_notes.py` (parità perimetro col vault), `verify_ingest.py`, `seed_audit_2026_07_31*.py` (21 task audit come dati, idempotenti) · `close_audit_2026_07_31.py` (chiusure per idempotency_key, con nota di chiusura)
- `mcp-connector/` — server MCP (5 tool `ovy_*`) · `SETUP-PRODUZIONE.md` — runbook produzione

## Comandi

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest -q                      # ~385 test offline (DB/LLM/rete mockati)
node scripts/test_console_headless.js    # il guardiano: apre DAVVERO la console (serve Playwright)
uvicorn app.main:app --reload --port 8000
curl -X POST localhost:8000/ingest -H "Authorization: Bearer $ADMIN_TOKEN"   # indicizza
```

## Regole tassative

1. **Mai committare** `.env`, `tenants.json`, PII, segreti (mai nemmeno in chat).
2. **Embeddings = Mistral** sempre; LLM Mistral o Claude via env; logica provider solo in `providers.py`.
3. **Accessi server-side**: lo scope è un filtro Qdrant, non un prompt. Il focus restringe soltanto. Il flag owner sta sul record del tenant, mai nella richiesta.
4. **Write-back solo con conferma umana**; contenuto nato da conversazione entra MARCATO «NON verificato» (lo marca il server).
5. **La console è UNA**: `panel/index.html` + `voce.js` + `brain3d.js` byte-identici nei due repo (sempre `cp` + commit su entrambi). La voce si modifica solo in `widget/voce.js`.
6. **GDPR**: Qdrant/region UE; contratti = dati personali → repo privato.
7. **Ogni consegna finisce in una PR aperta e VERIFICATA** (`list_pull_requests` dopo la creazione). Io non mergio mai: merge = Andrea. Se la PR del branch è già mergiata, si riparte da main (mai accodare a storia chiusa).
8. Prima di dire «fatto»: suite verde, guardiano headless verde, contract test verde.

## Stato (31-07-2026)

- ✅ In produzione: RAG multi-tenant, voce continua (frasi/barge-in a turni/mani libere/modo vocale; prima sillaba 55 ms), orbite+lenti+focus, conversazione libera owner, «Miglioramenti» (task audit 01-03, 09, 10 FATTE via `close_audit_*`; quadro di potenziamento collegato alla nota del vault), console che dichiara quando è pronta (riga `[boot]`; produzione 1265 ms), guardiano in CI, accessi cliente, ingest anti-stantio.
- ⏳ Aperti: task audit 04-08 e 11-21 (conversazione normale, sei sezioni, allarme cervello fermo, valore clienti, voce su telefono, case study Centioni, …), lente Temi (aspetta i tag `tema/*` decisi da Andrea — proposta in `docs/lenti-temi-proposta.md`), R2/R3 del piano nomi (migrazioni, non rename).

## Riferimenti

- Confronto e roadmap: `docs/confronto-divina-zoey.md` · voce: `docs/voce-continua.md`
- Audit in console: sezione «Miglioramenti» → «Gli audit» (`panel/audit-*.html`)
