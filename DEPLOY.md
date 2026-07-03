# Deploy di Ember su Railway

Servizio separato sullo stesso account Railway di FORMA. ~10 minuti.
Richiede il tuo account Railway e l'inserimento delle chiavi (azione tua: le credenziali non passano da me).

> **Cosa fa in cloud**: il servizio risponde a `/chat` usando Qdrant Cloud (già popolato) +
> Mistral. **Non** serve il vault in cloud: l'`/ingest` si lancia in locale dal Mac quando
> aggiorni le note. Quindi il deploy è leggero: solo l'app FastAPI + le variabili.

## Metodo consigliato — Railway CLI (`railway up`)

Niente secondo repo, niente token GitHub: la CLI carica la cartella e Railway la builda.
Rispetta `.railwayignore` (quindi `.env`, `.venv/`, `tenants.json` restano fuori).

Dal **Terminale del Mac**, una riga alla volta:

```bash
npm i -g @railway/cli            # installa la CLI (oppure: brew install railway)
railway login                    # apre il browser: accedi al tuo account Railway
cd "/Users/imac/Desktop/OVY-Cervello/chatbot-ember"
railway init                     # crea il progetto — chiamalo: ember
railway up                       # carica + builda + deploya
```

Quando il build finisce, genera il dominio pubblico:

```bash
railway domain                   # stampa https://ember-xxxx.up.railway.app
```

## Variabili d'ambiente

Impostale nella **dashboard** Railway (progetto → service → **Variables**) oppure via CLI
`railway variables --set "NOME=valore"`. I valori sono nel tuo `chatbot-ember/.env` locale.

| Variabile | Valore | Note |
|---|---|---|
| `LLM_PROVIDER` | `mistral` | non segreto |
| `EMBED_PROVIDER` | `mistral` | non segreto |
| `MISTRAL_API_KEY` | *(la tua chiave)* | **segreto** — dal tuo .env |
| `MISTRAL_LLM_MODEL` | `mistral-small-latest` | non segreto |
| `MISTRAL_EMBED_MODEL` | `mistral-embed` | non segreto |
| `QDRANT_URL` | *(endpoint cluster)* | dal tuo .env |
| `QDRANT_API_KEY` | *(chiave Qdrant)* | **segreto** — dal tuo .env |
| `QDRANT_COLLECTION` | `cervello` | deve combaciare con l'ingest |
| `ADMIN_TOKEN` | *(token forte)* | **segreto** — protegge /ingest |
| `TENANTS_JSON` | *(mappa tenant in JSON una riga)* | vedi sotto (o usa MongoDB) |
| `RATE_LIMIT_PER_MIN` | `30` | facoltativo |
| `MONGO_URI` | *(URI Atlas)* | **segreto** — tenant hashati + quote + revoca (consigliato) |
| `MONGO_DB` | `ember` | facoltativo |
| `VOICE_PROVIDER` | vuoto \| `elevenlabs` \| `deepgram` | attiva la voce PRO |
| `ELEVENLABS_API_KEY` / `DEEPGRAM_API_KEY` | *(chiave provider)* | **segreto** — solo se voce PRO |
| `VOICE_LANG` | `it` | lingua STT |

`VAULT_PATH` **non** serve in cloud.

### Tenant su MongoDB (consigliato) — chiavi hashate, quote, revoca

In alternativa a `TENANTS_JSON`, imposta `MONGO_URI` (Atlas, region UE). Le chiavi non si
salvano in chiaro: solo l'hash. Gestione con la CLI:

```bash
railway run python -m app.manage_tenants seed          # importa i tenant statici (hashati)
railway run python -m app.manage_tenants add "Cliente X" scopeX --origins https://www.clientex.it --quota 2000 --accent "#0ED4E4"
railway run python -m app.manage_tenants list
railway run python -m app.manage_tenants revoke "Cliente X"
railway run python -m app.manage_tenants rotate "Cliente X"
```

`add` e `rotate` stampano la chiave **una sola volta**: salvala subito.

### Voce PRO (opzionale)

Imposta `VOICE_PROVIDER=elevenlabs` (o `deepgram`) + la chiave del provider. Senza queste
variabili la voce PRO resta spenta e il widget usa la voce gratuita del browser (nessuna
rottura). Verifica: `curl .../health` → `"voice":"elevenlabs"`. Nel widget: `data-voice-mode="pro"`.

### TENANTS_JSON (la mappa tenant come variabile)

In cloud non c'è il file `tenants.json` (è gitignorato). Il codice legge la mappa dalla
variabile `TENANTS_JSON` se presente. Genera il valore (JSON su una riga) dal Mac:

```bash
cd "/Users/imac/Desktop/OVY-Cervello/chatbot-ember"
python3 -c "import json;print(json.dumps(json.load(open('tenants.json')),separators=(',',':'),ensure_ascii=False))"
```

Copia l'output e incollalo come valore di `TENANTS_JSON` in Railway.

## Verifica post-deploy

```bash
curl https://ember-xxxx.up.railway.app/health
# {"status":"ok","llm":"mistral","embed":"mistral"}

curl -X POST https://ember-xxxx.up.railway.app/chat \
  -H "X-Tenant-Key: <chiave FORMA>" -H "Content-Type: application/json" \
  -d '{"message":"Cosa fa FORMA?"}'
```

- ✅ FORMA risponde con le fonti.
- ✅ La chiave ATS **non** risponde su FORMA (isolamento scope).

## Dopo il go-live

- **CORS**: in `app/main.py` ora è `*` per il pilota. Restringi `allow_origins` ai domini di
  FORMA e ATS prima di pubblicare il widget.
- **Re-ingest**: quando aggiorni le note, lancia `/ingest` in locale (Qdrant Cloud si aggiorna
  e il servizio cloud vede subito i nuovi dati).
- **Aggiornare il codice in cloud**: ri-lancia `railway up` dalla cartella.

## Alternativa — Deploy da repo GitHub

Se preferisci l'auto-deploy ad ogni push (come per v4-forma): crea un repo privato dedicato,
fai push di `chatbot-ember/`, poi su Railway **New Project → Deploy from GitHub repo**.
Stesso set di variabili. Richiede un token GitHub con accesso a quel nuovo repo.
