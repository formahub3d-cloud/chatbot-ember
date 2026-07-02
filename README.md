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

- Ingestion da **upload/OCR** e **write-back** su vault+Notion → Fase 2.
- **Auto-compilazione** contratti da template → Fase 3.
- **Billing Stripe** + widget embeddabile + hardening GDPR → Fasi 1/4.
- Per GDPR: usa una **region Qdrant UE** e un host UE; i contratti contengono dati personali.
