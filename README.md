# Ember — Chatbot sul Cervello OVY

Motore RAG **multi-tenant** che risponde attingendo al cervello OVY (vault Obsidian),
con **accessi per settore**: ogni tenant (FORMA, ATS, HRH…) vede solo le aree consentite
dalla sua chiave. Provider-agnostico: LLM **Mistral** o **Claude**, embeddings **Mistral**.

> Questa è la **base Fase 0** (vedi `forma/docs/doc-chatbot-cervello` nel cervello).
> È pensata per diventare un **repo a sé** e girare come servizio separato su Railway.

## Architettura

```
note .md del cervello ──ingest──> Qdrant (vettori + scope)
                                      │
              domanda + chiave tenant │ retrieval filtrato per scope
                                      ▼
                          LLM (Mistral/Claude) ──> risposta + fonti
```

Lo **scope** è la chiave-permesso: `forma/clienti/ats/...` → scope `ats`; `forma/...` →
`forma-core`; `andrea-aloia/...` → `andrea`; `ovyon/...` → `ovyon`. Un tenant interroga
solo i propri scope: fuori area risponde "Non ho questa informazione".

## Integrazione OVYON (modello a tre livelli)

Ember è **il chatbot integrato in OVYON**. Lo `scope` mappa sul livello **`tenant`** del
modello OVYON (org > tenant > sotto-tenant): `ingest.segments_for` deriva dal path anche
`org` e `sub_tenant` in modo additivo, e `rag.build_filter` accetta grant a tre livelli
(retro-compatibile con `allowed_scopes`). Dettagli: `ovyon/docs/doc-ovyon-ember-scope` nel cervello.

**Endpoint per il connettore MCP** (stessa auth e stesso filtro per grant del `/chat`):

| Endpoint | Tool MCP | Cosa fa |
|---|---|---|
| `POST /search` | `ovy_search` | risultati (metadati + snippet) filtrati per grant |
| `GET /document?slug=` | `ovy_get_document` | nota completa per slug, se nello scope |
| `GET /context` | `ovy_list_context` | livelli org/tenant/sotto-tenant visibili |
| `POST /writeback` | `ovy_create/update_document` | scrive una nota **solo dopo conferma** (`confirm=true`) |

Il **connettore MCP** (server FastMCP) è in `mcp-connector/` (vedi il suo README).

**Flusso contratti (upload → conferma → write-back).** `POST /upload` fa OCR +
estrazione e restituisce l'**anteprima** dei campi (non consolida). Dopo la conferma
umana dei campi, `POST /contract/confirm` scrive la nota nel vault (cartella privata
del cliente, gitignorata) e — se `NOTION_TOKEN`/`NOTION_CONTRACTS_DB` sono configurati —
inserisce la riga nel **database Notion** dei contratti. Lo scope di destinazione
(`cliente`) deve essere tra quelli concessi al tenant.

**Backend Supabase (opzionale, `GRANTS_BACKEND=supabase` + `DATABASE_URL`).** Layer
identità/permessi/audit: risoluzione chiavi da `api_keys`, audit su `access_logs` in
sessione RLS, e sync dei metadati nota in `documents` durante l'ingest. Schema e istruzioni
in `db/` (`ovyon_schema.sql`, `README.md`). Setup completo di produzione: `OVYON-SETUP.md`.

## Setup

```bash
cd chatbot-ember
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env            # inserisci MISTRAL_API_KEY, QDRANT_URL, QDRANT_API_KEY, ADMIN_TOKEN
cp tenants.example.json tenants.json   # definisci le chiavi-tenant e i loro scope
```

Scelte rapide nel `.env`:
- `LLM_PROVIDER=mistral` (UE, economico) oppure `claude` (qualità top).
- `EMBED_PROVIDER=mistral` sempre (Claude non ha embeddings).
- `QDRANT_URL` = il tuo cluster (il **free tier basta** per iniziare).

## Avvio

```bash
uvicorn app.main:app --reload --port 8000
```

## Uso

Indicizza il cervello (una volta, e a ogni aggiornamento importante):

```bash
curl -X POST localhost:8000/ingest -H "Authorization: Bearer IL_TUO_ADMIN_TOKEN"
```

Chatta come tenant ATS (vede solo l'area ATS):

```bash
curl -X POST localhost:8000/chat \
  -H "X-Tenant-Key: CHIAVE_ATS" -H "Content-Type: application/json" \
  -d '{"message":"Chi ha un contratto in scadenza?"}'
```

Se chiedi al tenant ATS qualcosa di FORMA → risponde che non ha accesso. ✅

## Limiti di questa Fase 0 (prossimi passi)

- ✅ Ingestion da **upload/OCR** + **write-back** su vault e **Notion** (`/contract/confirm`) → Fase 2 fatta.
- **Auto-compilazione** contratti da template → Fase 3.
- **Billing Stripe** + widget embeddabile + hardening GDPR → Fasi 1/4.
- Per GDPR: usa una **region Qdrant UE** e un host UE; i contratti contengono dati personali.
