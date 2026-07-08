# DR-RUNBOOK — Backup & ripristino di Ember

> Cosa può rompersi, cosa perdi, come torni su. Backup con `python scripts/backup.py`
> (snapshot Qdrant + export JSON delle tabelle Supabase in `backup/AAAA-MM-GG/`).

## Cosa vive dove

| Dato | Dove | Perdita massima accettabile | Come si rigenera |
|---|---|---|---|
| Vettori del cervello | Qdrant (cloud UE) | Nessuna: **rigenerabile** | `POST /ingest` dal vault (fonte di verità = repo `ovy-cervello`) |
| Note del cervello | GitHub `ovy-cervello` (+ vault locale Obsidian) | Zero (già versionato) | è la fonte di verità |
| Tenant/chiavi/grant | Supabase `api_keys` | Bassa | export JSON (senza hash) + `manage_apikeys add` per riemettere le chiavi |
| Audit accessi / eventi / quote | Supabase `access_logs`, `analytics_events`, `key_usage` | Media (storico) | export JSON del backup |
| Metadati documenti | Supabase `documents` | Nessuna: **rigenerabile** | re-ingest (docstore sync) |
| Codice | GitHub `chatbot-ember` | Zero | redeploy Railway dal repo |

## Scenari

### 1. Qdrant perso/corrotto
1. Ricrea la collection (region **UE**).
2. `curl -X POST $EMBER/ingest -H "Authorization: Bearer $ADMIN_TOKEN"` → re-indicizza tutto dal vault.
3. Verifica: `python scripts/verify_ingest.py`.
In alternativa: ripristina l'ultimo snapshot dalla console Qdrant (Collections → Snapshots → Restore).

### 2. Supabase perso
1. Nuovo progetto Supabase (region UE) → applica `db/ovyon_schema.sql`.
2. Riemetti le chiavi tenant: `python -m app.manage_apikeys add <nome> ...` usando
   `backup/<data>/api_keys.json` come riferimento per grant/branding/quote
   (le chiavi in chiaro NON esistono da nessuna parte: vanno riemesse e ridistribuite).
3. Storico (facoltativo): reimporta i JSON di `access_logs`/`analytics_events`.
4. Aggiorna `DATABASE_URL` su Railway.

### 3. Railway perso
1. Nuovo servizio da GitHub `chatbot-ember` (branch `main`).
2. Reimposta le variabili da `.env.example` (chiavi reali dal password manager).
3. `GET /ready` verde → fine.

## Cadenza consigliata
- **Snapshot Qdrant**: prima di ogni re-ingest massivo (o settimanale). ⚠️ Non è
  ancora schedulato: si lancia a mano o da cron/CI con i secret.
- **Export Supabase**: settimanale, conservando le ultime 4 copie (i JSON contengono
  PII redatta ma trattali comunque come dati personali: restano fuori da Git, la
  cartella `backup/` è gitignorata).
