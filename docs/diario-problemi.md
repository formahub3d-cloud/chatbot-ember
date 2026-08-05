# Diario dei problemi — `divina-motore`

> Regola permanente (titolare, 05-08-2026): ogni problema o incongruenza trovata
> nel codice si **aggiusta** o si **segnala** qui. Stato: **RISOLTO** o **DA
> DECIDERE**. Ogni lavoro successivo parte da questo file.
>
> Voce nuova in cima. Chi risolve una voce «DA DECIDERE» la sposta a RISOLTO
> scrivendo cosa ha fatto — non la cancella: com'era prima è metà del racconto.

---

## 2026-08-05 · RISOLTO — La sorgente dei tenant si sceglieva sbagliando

**Dove:** `app/tenants.py` (`get_tenants`, `ensure_seeded`) · trovato in S1.1.

**Cosa succedeva.** `DATABASE_URL` punta a Supabase, dove `tenants` è la tabella
dello schema OVYON e non ha la colonna `key`. Ma `get_tenants()` provava lo
stesso la query storica `SELECT key, name, allowed_scopes FROM tenants` a ogni
scadenza di cache (60 s), prendeva l'eccezione e ripiegava sulla sorgente
statica. Risultato giusto (`TENANTS_JSON`, come confermato in dashboard), strada
sbagliata: uno stack trace ogni minuto e un comportamento corretto che dipendeva
da un errore. Chi un giorno «ripara» quell'eccezione cambia la sorgente dei
permessi senza averlo deciso.

**Il pezzo peggiore** era `ensure_seeded()`, che a ogni avvio faceva
`CREATE TABLE IF NOT EXISTS tenants (key TEXT PRIMARY KEY, …)` su qualunque
database trovasse. Su un Supabase vuoto — un ripristino, un ambiente nuovo —
avrebbe occupato il nome `tenants` con lo schema sbagliato, e l'orchestratore
(che si aspetta `tenant_id`/`org_id`) avrebbe risposto «tenant sconosciuto» per
sempre, senza che niente dicesse perché.

**Come è stato aggiustato.** Nuova `tenants_legacy()`: guarda una volta
`information_schema` e dice se la tabella ha la forma storica. Il DB si
interroga **solo** in quel caso; `ensure_seeded()` non crea più niente; una riga
di log all'avvio dichiara quale sorgente è in uso — prima non lo diceva nessuno.
Un «non so» (DB irraggiungibile) non finisce in cache come un «no».

Dove la forma storica c'è davvero, il comportamento è identico a prima.

**Prove:** `tests/test_tenants_legacy_pg.py` (4 casi, offline).
**Contesto:** `docs/mappa-dati-postgres-railway.md`.

---

## 2026-08-05 · RISOLTO — Il dump del Postgres storico non può entrare nel repo

**Dove:** S1.4, `scripts/snapshot_postgres_legacy.sh`.

Il task chiedeva «`pg_dump` → salva `postgres-legacy-snapshot.sql` nel
workspace». Ma la tabella `tenants` di quel database ha la colonna `key` con le
**chiavi-tenant in chiaro** (forma precedente ad `api_keys`, dove le chiavi
vivono hashate): committare quel dump violerebbe la regola tassativa n.1.

Risolto senza perdere il senso del task: lo script produce due file — il dump
completo (gitignorato, da custodire fuori dal repo) e
`postgres-legacy-inventario.md` con tabelle, conteggi e le chiavi ridotte al
loro sha256. La prova che lo snapshot esiste si committa; il segreto no.
Lo script verifica anche di essere completo (righe nel DB contro `INSERT` nel
dump) e si ferma se i conti non tornano.

---

## 2026-08-05 · DA DECIDERE — Le 4 chiavi del Postgres storico vanno riemesse?

Quelle chiavi sono state in chiaro in un database senza rotazione per mesi. Se
una è ancora attiva in `api_keys`, custodire meglio il dump non basta: andrebbe
riemessa (`scripts/reset_chiavi.py`, FORMA per prima, poi le altre — con il
freno già previsto dallo script).

Non l'ho fatto perché revocare una chiave è un'azione con effetto sui clienti e
non spetta a me deciderlo. Da valutare **dopo** lo snapshot (S1.4) e **prima**
di far entrare clienti paganti (Sprint 5).

---

## 2026-08-05 · DA DECIDERE — Le quote sono fail-open, e presto contano soldi

**Dove:** `app/tenants.py::quota_ok` → `_quota_ok_pg` / `_quota_ok_mongo`.

Se il database non risponde, la richiesta **passa**. Oggi è la scelta giusta:
la quota conta richieste, e negare un servizio per un problema nostro sarebbe
peggio del costo. Da Sprint 5 quel contatore diventa denaro, e lo stesso errore
regalerebbe fatturato.

Già previsto come S5.1c (fail-open → fail-closed) nel piano v1.1. Annotato qui
perché non si perda per strada: il momento giusto è **prima** del primo cliente
pagante, non dopo il primo conto sbagliato.
