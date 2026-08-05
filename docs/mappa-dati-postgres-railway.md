# S1.1 · Mappa dati del Postgres storico di Railway

> 05-08-2026 · Domanda del titolare: «conferma tu nel codice che nessun servizio
> lo legge». Risposta: **nessun servizio lo legge — ma il codice scritto per
> leggerlo era ancora vivo, e girava a vuoto contro Supabase.** Sotto le prove.

## 1. Cosa c'è dentro (dashboard, verificato dal titolare)

Una sola tabella, `tenants`, 4 righe, ~16 KB. Zero connessioni applicative.

## 2. Da dove viene quella tabella

Da questo repo. `app/tenants.py::ensure_seeded()` girava a **ogni avvio** e
faceva, su qualunque database puntato da `DATABASE_URL`:

```sql
CREATE TABLE IF NOT EXISTS tenants (key TEXT PRIMARY KEY, name TEXT, allowed_scopes JSONB NOT NULL)
```

È la forma **storica** del tenant store, precedente allo schema OVYON. Quando
`DATABASE_URL` puntava al Postgres di Railway, quella tabella è nata lì e si è
popolata dalla sorgente statica. Il fossile ha esattamente la forma dello
strumento che l'ha prodotto — 4 righe, una per tenant.

## 3. Chi apre una connessione Postgres, oggi

Due variabili in tutto il sistema, una per servizio. Non esiste da nessuna parte
una seconda stringa di connessione, né un riferimento a un host Railway.

| Servizio | Variabile | Dove si usa |
|---|---|---|
| `divina-motore` | `DATABASE_URL` | `app/tenants.py::_conn()` — la usano `brain`, `braintasks`, `clientauth`, `clientkb`, `memoria`, `riassunti`, `docstore`, `rls` |
| `divina-agenti` | `DIVINA_DATABASE_URL` | `app/db.py::_connect()` — unico punto |

Ne segue che **il Postgres storico è raggiungibile solo se una di quelle due
variabili punta lì**: è una questione di configurazione, non di codice. E la
configurazione dice Supabase, per due prove indipendenti:

1. `divina-agenti` risolve i tenant con
   `SELECT t.tenant_id, t.org_id … FROM tenants t JOIN organizations o ON o.org_id = t.org_id`.
   Contro la tabella storica (che ha `key`, non `tenant_id`, e non ha
   `organizations` accanto) quella query fallirebbe e **ogni** rotta
   dell'orchestratore risponderebbe «tenant sconosciuto». Non succede.
2. Il motore usa su quella stessa connessione `brain_tasks`, `client_access`,
   `tenant_flags`, `conversation_summary` — tabelle che nel Postgres storico non
   esistono (c'è solo `tenants`), e che `app/dbcheck.py` dichiarerebbe mancanti
   all'avvio.

**Conclusione S1.1: nessun servizio legge il Postgres storico. Spegnerlo (S1.6)
non tocca nessun percorso di codice.**

## 4. Il difetto trovato strada facendo (risolto oggi)

`DATABASE_URL` punta a Supabase, dove `tenants` è la tabella dello schema OVYON
— senza colonna `key`. Ma `get_tenants()` provava lo stesso la query storica:

```python
if settings.database_url.strip():
    try:        data = load_db()          # SELECT key, name, allowed_scopes FROM tenants
    except Exception:
        log.exception(...)                # ← qui, ogni 60 secondi
        data = load_static()              # ← e la sorgente vera era questa
```

La sorgente in produzione **è** `TENANTS_JSON`, come da verifica del titolare —
ma ci si arrivava **per la via di un errore**: uno stack trace a ogni scadenza di
cache, e un comportamento corretto che dipendeva da un fallimento. Il giorno che
qualcuno «ripara» quell'eccezione, il sistema cambia sorgente senza che nessuno
l'abbia deciso.

Il guasto peggiore era però l'altro: `ensure_seeded()` **creava** la tabella
storica su qualunque database trovasse. Su un Supabase vuoto (un ripristino, un
ambiente nuovo) avrebbe occupato il nome `tenants` con lo schema sbagliato, e
l'orchestratore sarebbe diventato cieco senza che niente dicesse perché.

**Cosa è cambiato** (`app/tenants.py`, test `tests/test_tenants_legacy_pg.py`):

- nuova `tenants_legacy()` — guarda **una volta** `information_schema` e dice se
  la tabella ha la forma storica. Un «non so» (DB irraggiungibile) non viene
  messo in cache come un «no»;
- `get_tenants()` interroga il DB **solo** se quella forma c'è. Altrimenti va
  diritto alla sorgente statica, senza eccezioni;
- `ensure_seeded()` **non crea più la tabella**. Se la forma storica c'è, la
  popola come prima; altrimenti non fa niente;
- una riga di log all'avvio dice quale sorgente è in uso. Prima non lo diceva
  nessuno.

Dove la forma storica esiste davvero, il comportamento è identico a prima: c'è
un test che lo dimostra (`test_tabella_storica_ancora_sorgente_del_db`).

## 5. S1.4 — lo snapshot, e perché non si committa

`scripts/snapshot_postgres_legacy.sh`. **Non eseguito qui**: questo ambiente non
ha la Railway CLI né credenziali verso quel database. Lo lancia chi ha accesso.

Il punto da non saltare: **la colonna `key` contiene le chiavi-tenant in
chiaro** — è la forma precedente ad `api_keys`, dove invece le chiavi vivono
hashate. Un `pg_dump` di quella tabella è un segreto, e la regola tassativa n.1
di questo repo vieta di committarlo.

Quindi lo script produce due file:

| File | Dove va |
|---|---|
| `postgres-legacy-snapshot.sql` | dump completo — **gitignorato**, da custodire fuori dal repo (storage cifrato / password manager) |
| `postgres-legacy-inventario.md` | tabelle, conteggi, e le chiavi ridotte al loro sha256 — **questo si committa**, ed è la prova che lo snapshot esiste |

Lo script verifica da solo di essere completo (righe contate nel database contro
`INSERT` ritrovati nel dump) e **si ferma con errore** se i due numeri non
combaciano: uno snapshot che non si sa se è intero non autorizza a spegnere
niente.

### Sequenza per chiudere Fase 1

```bash
export DATABASE_URL='postgresql://…'          # DSN del Postgres STORICO
./scripts/snapshot_postgres_legacy.sh          # dump + inventario + verifica
mv postgres-legacy-snapshot.sql <storage cifrato fuori dal repo>
git add postgres-legacy-inventario.md && git commit
# solo adesso: S1.6 — cancellazione del servizio dalla dashboard Railway
```

Nota di sicurezza per il dopo: quelle 4 chiavi in chiaro sono comunque da
considerare **compromesse per anzianità** (sono state in un database senza
rotazione per mesi). Se una di esse è ancora attiva in `api_keys`, la strada
giusta non è custodirla meglio: è riemetterla con `scripts/reset_chiavi.py`
(FORMA prima, poi le altre). Da decidere — annotato in `docs/diario-problemi.md`.
