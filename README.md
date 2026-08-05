# Divina — il motore (`divina-motore`)

Motore RAG **multi-tenant** che risponde attingendo al cervello di Divina (un vault Obsidian),
con **accessi per settore**: ogni tenant (FORMA, ATS, HRH…) vede solo le aree consentite
dalla sua chiave. Provider-agnostico: LLM **Mistral** o **Claude**, embeddings **Mistral**.

Oltre al RAG, qui vivono: ingest del vault, voce (STT/TTS), upload e OCR, accessi
cliente, coda task, e la console `/panel/`. Gira su `divina.formahub.it`.

## L'ecosistema in quattro repo

| Repo | Cos'è | Dove gira |
|---|---|---|
| [`v4-forma`](https://github.com/formahub3d-cloud/v4-forma) | sito + CRM + (in arrivo) **area cliente Divina** | `www.formahub.it` · `api.formahub.it` |
| **`divina-motore`** (qui) | motore RAG, cervello, voce, console | `divina.formahub.it` |
| [`divina-agenti`](https://github.com/formahub3d-cloud/divina-agenti) | orchestratore: i 3 companion, nodi, documenti | servizio Railway |
| [`divina-cervello`](https://github.com/formahub3d-cloud/divina-cervello) | il vault Obsidian: la sorgente delle note | repo (privato) |

Nomi storici ancora vivi nei **contratti** e da NON rinominare: `MONGO_DB=ember`,
`EMBER_URL`/`EMBER_ADMIN_TOKEN`, logger `ember`, tool MCP `ovy_*`, schema e GUC
SQL `ovyon.*`, cartella `ovyon/` del vault (è uno scope, cioè un permesso).

## Direzione: rebuild Divina v3.1

Divina diventa un prodotto vendibile: l'area cliente si costruisce dentro
`v4-forma` (`app.divina.formahub.it`) con identità FORMA unica e uso misurato in
**token**. Questo servizio **resta** — è qui che vivono chat, fonti, memoria,
documenti e voce — e continua a rispondere su `divina.formahub.it` finché la
console non va in pensione (S7.3). Documenti vincolanti (super prompt v3.1 ·
piano sprint v1.1) fuori repo; qui dentro:

- `docs/stato-reale-divina-motore.md` — cos'è oggi questo servizio, in una pagina.
- `docs/diario-problemi.md` — **si parte da qui**: problemi trovati, risolti o da decidere.
- `docs/mappa-dati-postgres-railway.md` — S1.1: perché il Postgres storico si può spegnere.
- `scripts/snapshot_postgres_legacy.sh` — S1.4: lo snapshot prima di spegnerlo.
- Il contratto con il backend FORMA sta in `divina-agenti/openapi.yaml`.

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

## Il modello a tre livelli (org · tenant · sub_tenant)

Lo `scope` mappa sul livello **`tenant`** del
modello a tre livelli (org > tenant > sotto-tenant): `ingest.segments_for` deriva dal path anche
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

**Backend Supabase (opzionale, `GRANTS_BACKEND=supabase` + `DATABASE_URL`).** Layer
identità/permessi/audit: risoluzione chiavi da `api_keys`, audit su `access_logs` in
sessione RLS, e sync dei metadati nota in `documents` durante l'ingest. Schema e istruzioni
in `db/` (`schema.sql`, `README.md`). Setup completo di produzione: `SETUP-PRODUZIONE.md`.

## Setup

```bash
cd divina-motore
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

- Ingestion da **upload/OCR** e **write-back** su vault+Notion → Fase 2.
- **Auto-compilazione** contratti da template → Fase 3.
- **Billing Stripe** + widget embeddabile + hardening GDPR → Fasi 1/4.
- Per GDPR: usa una **region Qdrant UE** e un host UE; i contratti contengono dati personali.
