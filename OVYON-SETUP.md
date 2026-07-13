# OVYON / Divina — Runbook di provisioning (per Cowork)

> Questo file è anche il **prompt da dare a Cowork**: la sezione qui sotto è
> auto-contenuta. Cowork guida/esegue la parte manuale (account, credenziali, DNS,
> collegamento MCP a Claude); il codice è già scritto e testato nei due repo.

---

## PROMPT PER COWORK (incolla da qui)

Sei l'assistente operativo per portare in produzione **OVYON / Divina**. Contesto:

- **OVY** = cervello (vault Obsidian), repo `formahub3d-cloud/ovy-cervello`.
- **Divina** = chatbot multi-tenant integrato in OVYON, repo `formahub3d-cloud/chatbot-ember`.
- Branch di lavoro in entrambi: `claude/ovyon-architecture-ip-puowot`.
- Il codice dei passi 1–5 è già scritto e testato. **Serve solo la parte manuale**:
  creare i servizi esterni, raccogliere le credenziali, applicare lo schema SQL,
  deployare, e collegare il connettore MCP a Claude.

**Regole:** region **UE** ovunque possibile (GDPR). **Mai** committare segreti
(`.env`, `tenants.json`, chiavi, DATABASE_URL): metterli come variabili/secret nei
servizi. Alla fine consegna tutti i valori raccolti in un password manager.

Esegui gli step in ordine; ad ogni step raccogli i **valori richiesti** e verifica.

### Step 1 — Qdrant Cloud (vector DB, region UE)
- Crea un cluster Qdrant Cloud in **Europa**.
- Raccogli: `QDRANT_URL`, `QDRANT_API_KEY`.

### Step 2 — Provider LLM/embeddings
- Mistral (obbligatorio, embeddings + LLM): `MISTRAL_API_KEY`.
- Anthropic (opzionale, se si vuole LLM Claude): `ANTHROPIC_API_KEY`.

### Step 3 — Supabase (identità/permessi/audit, region UE)
- Crea un progetto Supabase in **Europa**. Raccogli: project URL, `DATABASE_URL`
  (connection string Postgres), `service_role` key, `anon` key.
- Applica lo schema: nel SQL editor esegui il contenuto di `db/ovyon_schema.sql`,
  poi (per un ambiente di prova) `db/seed.example.sql`.
- Decisione RLS: per l'isolamento reale, Divina deve connettersi con un ruolo su cui
  la RLS è attiva **oppure** impostare i GUC `ovyon.*` per richiesta (vedi `db/README.md`).
  Annota la scelta.

### Step 4 — Chiavi-tenant reali
- Genera una chiave per ogni tenant (FORMA interno, ATS, HRH…). Formato consigliato:
  `ember_<random>`. In locale puoi usare: `python -c "from app.security import new_key; print(new_key())"`.
- Inserisci in Supabase `api_keys` la riga con `key_hash` = sha256 della chiave
  (`select encode(digest('<chiave>','sha256'),'hex')`) e i grant
  (`allowed_tenants`, `allowed_orgs`, `allowed_sub_tenants`, `allowed_origins`).
- Consegna in modo sicuro la chiave di **ATS** (pilota) e quella di FORMA interno.

### Step 5 — Consegna del vault a Divina
> **Decisione di architettura da confermare con l'utente.** Divina indicizza il vault
> dal path `VAULT_PATH`. Su Railway il vault non è presente: scegliere come fornirlo.
- Opzione consigliata (MVP): al deploy, **clona `ovy-cervello`** (branch main) in una
  cartella e punta `VAULT_PATH` lì; re-indicizza a ogni aggiornamento del cervello.
- Alternativa: sync periodico / volume. Annota la scelta e imposta `VAULT_PATH`.

### Step 6 — Deploy di Divina su Railway
- Deploy del servizio dal repo `chatbot-ember` (Procfile già presente: uvicorn).
- Imposta le variabili d'ambiente (come **secret**, non nel repo):
  `MISTRAL_API_KEY`, (`ANTHROPIC_API_KEY`), `QDRANT_URL`, `QDRANT_API_KEY`,
  `QDRANT_COLLECTION` (default `cervello`), `VAULT_PATH`, `ADMIN_TOKEN` (forte),
  `CORS_ORIGINS` (domini reali dei widget), e per i tenant **una** tra:
  `DATABASE_URL` (Supabase) · `MONGO_URI` · `TENANTS_JSON`.
- Verifica: `GET /health` risponde `{"status":"ok"}`.

### Step 7 — Indicizzazione del cervello
- `curl -X POST https://<dominio>/ingest -H "Authorization: Bearer $ADMIN_TOKEN"`.
- Deve rispondere `{"notes": N, "chunks": M}`. La re-ingest è **additiva**: il payload
  Qdrant ora include `org`/`tenant`/`sub_tenant`.
- Verifica scope: `POST /chat` con `X-Tenant-Key: <chiave ATS>` → vede solo ATS;
  `POST /search` con la stessa chiave → risultati filtrati.

### Step 8 — Connettore MCP → Claude
- In `mcp-connector/`: `pip install -r requirements.txt`, copia `.env.example` in
  `.env`, imposta `EMBER_API_URL=https://<dominio>` e `EMBER_TENANT_KEY=<chiave tenant>`.
- Aggiungi il server alla config MCP di Claude Desktop/Code (esempio in
  `mcp-connector/README.md`).
- Verifica dai tool in chat: `ovy_list_context`, poi `ovy_search`, `ovy_get_document`.
  Prova `ovy_create_document` con `confirm=false` (deve tornare l'anteprima) e, dopo
  approvazione, `confirm=true`.

### Step 9 — (Opzionale) Dominio ovyon.it
- DNS: `app.ovyon.it`, `api.ovyon.it`, `docs.ovyon.it` (Sez. 16 del doc). Raccogli i record.

### Step 10 — (Opzionale) Notion write-back
- `NOTION_TOKEN`, `NOTION_CONTRACTS_DB` (database "Contratti ATS"). Solo dopo DPA.

### Step 11 — GDPR / legale (umano)
- Revisione legale del trasferimento IP (Sez. 14) e **DPA** per i contratti prima di
  indicizzare dati personali (togliere `contratti` da `SKIP_DIRS` solo dopo).

### Consegna finale
Raccogli in un password manager: tutte le chiavi API, `DATABASE_URL`, `ADMIN_TOKEN`,
le chiavi-tenant (in chiaro, consegnate ai rispettivi referenti) e le decisioni prese
(ruolo RLS, consegna vault, dominio). Conferma che nessun segreto è finito in git.

--- fine prompt per Cowork ---

## Cosa NON serve fare a mano (già pronto nel codice)
- Mappatura scope→org/tenant/sub_tenant, filtro per grant, endpoint MCP, connettore,
  schema SQL + RLS, write-back con conferma. Vedi `ovyon/docs/doc-ovyon-ember-scope`
  nel cervello per lo stato dettagliato.
