# S0.3 · Stato reale — `divina-motore` (motore RAG + cervello)

> 05-08-2026 · letto dal codice. Verdetti trasversali:
> `divina-agenti/docs/assunzioni-super-prompt-v3.md`.

## Cos'è, in una riga

Il servizio più grande dei tre: chatbot RAG multi-tenant, ingest del vault in
Qdrant, voce, upload/OCR, accessi cliente, coda task, billing Stripe legacy, e la
console `/panel/`. ~50 moduli, ~524 test offline. È quello che oggi risponde su
`divina.formahub.it`.

## Superficie API (≈80 rotte)

| Gruppo | Rotte principali |
|---|---|
| Pubblico/widget | `GET /health` · `GET /config` · `POST /chat` (SSE) · `POST /chat/chiudi` · `POST /voice/stt` · `POST /voice/tts` |
| MCP | `POST /search` · `GET /document` · `GET /context` · `POST /writeback` |
| Documenti | `POST /upload` · `POST /upload/confirm` · `POST /ingest` |
| Cliente | `POST /client/login` · `GET /client/me` · `GET /client/kb` · `POST /client/segnala` · `GET /client/buchi` · `POST /client/chat` |
| Admin | `/admin/status` · `/admin/brain*` · `/admin/tasks*` · `/admin/proposals*` · `/admin/memoria*` · `/admin/clients*` · `/admin/tenants*` · `/admin/gdpr/*` · `/admin/usage` · `/admin/access-logs` |
| Billing | `POST /billing/checkout` · `POST /billing/webhook` |

Autenticazione a **tre modelli distinti**: chiave tenant (`X-Tenant-Key`) per il
widget, `Authorization: Bearer ADMIN_TOKEN` per l'admin, cookie HMAC firmato per
gli accessi cliente (`app/clientauth.py`).

## Dati — attenzione, sono due store

1. **Supabase Postgres** (schema `ovyon`, RLS): `organizations`, `tenants`,
   `sub_tenants`, `documents`, `access_logs`, `analytics_events`, `key_usage`,
   `api_keys` + le migrazioni successive (`brain_tasks*`, `brain_graph`,
   `client_access`, `client_report`, `conversation_summary`, `ingest_meta`,
   `tenant_flags*`, `tenant_memory`).
2. **MongoDB opzionale** (`MONGO_URI`, `MONGO_DB=ember`): store tenant + quote
   alternativo che, quando è valorizzato, **ha la precedenza su Postgres**
   (`app/tenants.py`, `_quota_check`). Da verificare se è acceso in produzione:
   se sì, «Supabase unico DB» ha un pezzo in più da migrare (§A delle assunzioni).
3. **Qdrant**: i vettori. Il filtro per scope è server-side (`rag.build_filter`);
   il focus restringe soltanto, mai allarga.

`app/dbcheck.py` confronta le migrazioni **attese** con quelle applicate e dichiara
cosa manca; `app/degrado.py` fa la stessa cosa a livello di funzione (acceso ·
spento · non-so) e lo dice **dove la funzione si usa**. Sono due strumenti da
riusare nell'area nuova, non da rifare.

## Quote — contano richieste, non token

`api_keys.quota_day` + `branding.quota_month` + tabella `key_usage(key_hash,
period, count)`, incremento atomico, verifica in `tenants.quota_ok()` su ogni
`/chat`, `/voice/*`, `/search`. **Fail-open**: se il DB non risponde, la richiesta
passa. Nessun conteggio di token LLM in `app/providers.py`; `app/costs.py` è una
stima dichiarata (richieste × tariffa media da env), non contabilità.

Quando i token diventano denaro (S5), il fail-open va invertito: oggi un errore DB
regala consumo, domani regalerebbe fatturato.

## Stripe legacy

`app/billing.py` + `/billing/checkout` + `/billing/webhook`, price
`starter`/`pro`/`enterprise` (+ setup fee opzionale), inerte senza
`STRIPE_SECRET_KEY`. **Non** si chiamano Dante/Virgilio/Beatrice: quelli sono gli
agenti e `branding.tier`, che modula solo lo stile della risposta e non tocca i
grant. È questo billing che S5.3 deve deprecare; il nuovo vive in v4-forma.

## Accessi cliente — il pezzo da trasportare, non da buttare

`app/clientauth.py` + `db/client_access.sql`: FORMA provisiona, primo accesso con
email+password, poi **PIN a 6 cifre** e la password si disattiva. Cookie HttpOnly
firmati (12h cliente, 30' ghost), scrypt, lockout a 5 tentativi, nessun DELETE.
La riga custodisce anche **`tenant_key_enc`**, cioè il legame utente→scope cifrato:
ritirare il metodo di login (S2.8) significa trasportare quel legame dentro
l'identità FORMA (§E delle assunzioni).

## Console — non è portabile per copia

`panel/index.html` è una SPA in **un file unico, senza build**, servita con una CSP
che ammette `unsafe-inline`. v4-forma impone invece una CSP strict a **nonce
per-request** (`middleware.ts`). Le viste admin utili (S7.1) vanno **riscritte** in
React/shadcn: si trasporta il contenuto (query, tabelle, etichette), non il codice.
I tre file della console (`index.html`, `voce.js`, `brain3d.js`) si modificano
**qui** e si copiano nell'orchestratore, col manifesto `CONSOLE.sha256`.

## Test e CI

~524 test offline (DB/LLM/rete mockati) + il **guardiano headless**
(`scripts/test_console_headless.js`, apre davvero la console con Playwright e
preme i pulsanti) + `contract_console.py` (zero endpoint fantasma, ogni rotta
dichiara chi la chiama) + `console_parita.py`. Workflow: `ci.yml`, `audit-merge.yml`,
`eval.yml`, `nightly-retention.yml`, `reingest.yml`.

**Regola V11/10 da rispettare anche nel lavoro nuovo:** una rotta nuova senza
dichiarazione di chiamante fa fallire la CI (`contract_console.py` →
`orfane()`/`CHIAMANTI_FUORI`).

## Cosa serve costruire qui (dal piano)

- **S3.2/S3.3** — la chat resta qui: `/chat` ha già streaming SSE, fonti, `gap`,
  memoria, filo, capacità. Il backend FORMA la consuma; il badge fonte e la
  risposta divisa in due sezioni si costruiscono su quello che già ritorna.
- **S4.1** — i documenti restano qui (`/upload`, `/upload/confirm`, OCR, writeback).
- **S5.1** — `app/providers.py` deve leggere `usage` dalle risposte dei modelli.
- **S5.3** — deprecare `/billing/*`.
- **S7.3** — il dominio `divina.formahub.it` è servito da qui: lo switch va
  pianificato, non improvvisato (§I delle assunzioni).
