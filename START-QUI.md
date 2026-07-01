# START-QUI — I passi che fai TU adesso

Ordine consigliato. I passi 1–2 sono "browser" (li puoi fare anche con me in Cowork);
i passi 3–6 sono in **Claude Code** dentro questa cartella.

---

## 1) Chiave Mistral (LLM + OCR + embeddings)

1. Vai su **console.mistral.ai** → crea account (o accedi).
2. Sezione **API Keys** → *Create new key* → **copia** la chiave.
3. Tienila da parte: andrà in `.env` come `MISTRAL_API_KEY`.

## 2) Cluster Qdrant (database vettoriale, free)

1. Vai su **cloud.qdrant.io** → crea account.
2. *Create cluster* → piano **Free** → **scegli una region UE** (importante per il GDPR).
3. Copia **URL del cluster** e crea/copia la **API key**.
4. Andranno in `.env` come `QDRANT_URL` e `QDRANT_API_KEY`.

> Account e chiavi li crei tu: io (Claude) non creo account né inserisco credenziali.

## 3) Apri il progetto in Claude Code

```bash
cd "/Users/imac/Desktop/OVY-Cervello/chatbot-jarvis"
claude
```

## 4) Configura le chiavi

```bash
cp .env.example .env
cp tenants.example.json tenants.json
```
Apri `.env` e incolla: `MISTRAL_API_KEY`, `QDRANT_URL`, `QDRANT_API_KEY`,
e scegli un `ADMIN_TOKEN` (una password a tua scelta per il comando di indicizzazione).
Lascia `LLM_PROVIDER=mistral` e `VAULT_PATH` già puntato al cervello.

## 5) Installa e avvia (può farlo Claude Code per te)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## 6) Indicizza il cervello e fai la prima domanda

```bash
# indicizza (usa il tuo ADMIN_TOKEN):
curl -X POST localhost:8000/ingest -H "Authorization: Bearer IL_TUO_ADMIN_TOKEN"

# prova come tenant ATS (vede solo ATS):
curl -X POST localhost:8000/chat \
  -H "X-Tenant-Key: CHIAVE_ATS" -H "Content-Type: application/json" \
  -d '{"message":"Chi ha lavorato il 13 giugno?"}'
```
Se chiedi al tenant ATS qualcosa di FORMA → deve rispondere che non ha accesso. ✅

## 7) Rendi il progetto un repo PRIVATO (separato dal cervello)

```bash
git init && git add -A && git commit -m "Jarvis Fase 0+2"
```
Poi crea un repo su GitHub **privato** e collegalo. (Il push/collegamento possiamo
farlo insieme in Cowork.)

---

## Cosa faccio IO in Cowork (browser/collegamenti)

- Repo del **cervello** privato + push + revoca token (rimasto aperto).
- Aiuto con **Railway** (servizio separato per Jarvis) e il collegamento al repo.
- **Token Notion** per il write-back (Fase 2b).
- Gestione contratti, Notion, Obsidian, ricerche.

Quando hai le chiavi Mistral + Qdrant, dimmelo: proseguiamo.
