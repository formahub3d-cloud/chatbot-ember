# Deploy di Jarvis su Railway

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
cd "/Users/imac/Desktop/OVY-Cervello/chatbot-jarvis"
railway init                     # crea il progetto — chiamalo: jarvis
railway up                       # carica + builda + deploya
```

Quando il build finisce, genera il dominio pubblico:

```bash
railway domain                   # stampa https://jarvis-xxxx.up.railway.app
```

## Variabili d'ambiente

Impostale nella **dashboard** Railway (progetto → service → **Variables**) oppure via CLI
`railway variables --set "NOME=valore"`. I valori sono nel tuo `chatbot-jarvis/.env` locale.

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
| `TENANTS_JSON` | *(mappa tenant in JSON una riga)* | vedi sotto |
| `RATE_LIMIT_PER_MIN` | `30` | facoltativo |

`VAULT_PATH` **non** serve in cloud.

### TENANTS_JSON (la mappa tenant come variabile)

In cloud non c'è il file `tenants.json` (è gitignorato). Il codice legge la mappa dalla
variabile `TENANTS_JSON` se presente. Genera il valore (JSON su una riga) dal Mac:

```bash
cd "/Users/imac/Desktop/OVY-Cervello/chatbot-jarvis"
python3 -c "import json;print(json.dumps(json.load(open('tenants.json')),separators=(',',':'),ensure_ascii=False))"
```

Copia l'output e incollalo come valore di `TENANTS_JSON` in Railway.

## Verifica post-deploy

```bash
curl https://jarvis-xxxx.up.railway.app/health
# {"status":"ok","llm":"mistral","embed":"mistral"}

curl -X POST https://jarvis-xxxx.up.railway.app/chat \
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
fai push di `chatbot-jarvis/`, poi su Railway **New Project → Deploy from GitHub repo**.
Stesso set di variabili. Richiede un token GitHub con accesso a quel nuovo repo.
