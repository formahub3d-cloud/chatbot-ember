# RUNBOOK — Ambiente di STAGING per Ember

> Obiettivo: provare le modifiche in un ambiente identico alla produzione ma
> **isolato** (dati e chiavi separati), prima del merge su `main`.
> Tutto è pronto lato codice: l'attivazione richiede ~10 minuti sui tuoi account. 🔒

## Ricetta (Railway)

1. **Nuovo servizio** nello stesso progetto Railway → "Deploy from GitHub repo"
   → `formahub3d-cloud/chatbot-ember`, branch **`staging`**
   (crea il branch da main: `git branch staging && git push origin staging`).
2. **Variabili**: copia quelle del servizio di produzione, POI cambia:
   - `QDRANT_COLLECTION=cervello_staging` (stesso cluster va bene: collection separata)
   - `ADMIN_TOKEN` → token diverso dalla produzione
   - `GRANTS_BACKEND=static` + `tenants.json` di prova (oppure un progetto Supabase di test)
   - `ANALYTICS_PERSIST=false`, `SENTRY_DSN` vuoto (o progetto Sentry separato)
   - `COST_ALERT_DAILY_EUR` basso (es. 1) per accorgersi dei loop
3. **Dominio**: usa quello generato da Railway (es. `ember-staging.up.railway.app`) —
   nessun DNS da toccare.
4. **Popola**: `curl -X POST https://<staging>/ingest -H "Authorization: Bearer <token staging>"`.
5. **Collaudo**: `GET /ready` verde → prova `/chat` con una chiave di test →
   `python scripts/eval_rag.py --base https://<staging>` (vedi eval).

## Flusso di lavoro

```
feature branch → push → CI (pytest) → merge su staging → prova su ember-staging
                                            ↓ ok
                                      merge su main → deploy produzione
```

## Regole
- In staging **niente dati reali dei clienti** (GDPR): solo contenuti di prova.
- Le chiavi tenant di staging non devono mai finire in siti pubblici.
- Lo staging può stare spento quando non serve (Railway: "Remove deployment").
