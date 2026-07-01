# CLAUDE.md — Contesto progetto per Claude Code

> Leggi questo file prima di lavorare. È il contesto del progetto **Jarvis**.

## Cos'è

**Jarvis** è un chatbot AI **multi-tenant** che risponde attingendo al "cervello OVY"
(un vault Obsidian di Andrea Aloia / FORMA). È un **prodotto FORMA**: FORMA lo usa
internamente (tenant 0), **ATS** è il pilota, poi si vende ai clienti.

Regola d'oro del prodotto: **un solo motore, molte chiavi.** Ogni cliente è un *tenant*
con una chiave che limita le **aree** del cervello che può leggere (separazione per settore).

## Architettura

```
note .md del cervello ──ingest──> Qdrant (vettori + "scope")
                                       │ retrieval filtrato per scope
        domanda + chiave tenant ──────►│
                                       ▼
                           LLM (Mistral/Claude) ──> risposta + fonti
upload documento ──OCR──► estrazione campi ──(conferma umana)──► write-back vault/Notion
```

**Scope = permesso.** Calcolato dal path della nota:
`forma/clienti/<X>/…` → `<X>` (es. `ats`); `forma/…` → `forma-core`;
`andrea-aloia/…` → `andrea`; `ovyon/…` → `ovyon`.
Un tenant vede solo i suoi `allowed_scopes` (in `tenants.json`).

## Mappa file

- `app/config.py` — settings da `.env`
- `app/providers.py` — embeddings + chat (switch Mistral/Claude)
- `app/ingest.py` — legge il vault, calcola lo scope, chunk + embed → Qdrant
- `app/rag.py` — retrieval filtrato per scope + risposta vincolata al contenuto
- `app/ocr.py` — OCR documenti (Mistral OCR)
- `app/extract.py` — estrazione campi (regex UniLav + LLM generico)
- `app/writeback.py` — scrive la nota nel vault (Notion = TODO)
- `app/main.py` — API: `/health` `/ingest` `/chat` `/upload`

## Comandi

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # poi inserisci le chiavi
cp tenants.example.json tenants.json
uvicorn app.main:app --reload --port 8000
# indicizza il cervello:
curl -X POST localhost:8000/ingest -H "Authorization: Bearer $ADMIN_TOKEN"
# chatta come ATS (vede solo ATS):
curl -X POST localhost:8000/chat -H "X-Tenant-Key: CHIAVE_ATS" \
     -H "Content-Type: application/json" -d '{"message":"..."}'
```

## Regole tassative

1. **Mai committare** `.env`, `tenants.json`, né dati personali (PII). Sono già in `.gitignore`.
2. **Embeddings = Mistral** sempre (Claude non ha embeddings nativi). LLM = Mistral o Claude via env.
3. **Provider-agnostico:** non incollare logica specifica di un fornitore fuori da `providers.py`.
4. **Accessi server-side:** lo scope non si fa col prompt, si fa col filtro su Qdrant.
5. **Write-back solo dopo conferma umana** dei campi (specie CF e codice comunicazione).
6. **GDPR:** usare region **UE** per Qdrant; i contratti sono dati personali → repo PRIVATO.
7. Questo servizio è **separato dal sito FORMA**; deploy come servizio a sé su Railway.

## Stato attuale

- ✅ Fase 0 (RAG single/multi-tenant) e ✅ Fase 2 codice (OCR/estrazione/upload) presenti.
- ⏳ Da fare: collaudo con chiavi reali, widget (Fase 1), write-back Notion (Fase 2b),
  auto-compilazione (Fase 3), billing + GDPR (Fase 4).

## Riferimenti nel cervello

- Architettura/costi/roadmap: `../forma/docs/doc-chatbot-cervello.md`
- Audit visivo: `../audit-chatbot-jarvis.html`
