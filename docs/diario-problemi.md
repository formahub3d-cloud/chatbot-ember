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

## 2026-08-05 · DA DECIDERE — Piano di rotazione delle 4 chiavi storiche

**Istruzione ricevuta:** verificare quali delle quattro sono ancora attive in
`api_keys`; ruotare subito le **inattive**; per le **attive** proporre un piano e
lasciare decidere il titolare (impatta i clienti).

**Cosa serve per eseguirla, e perché non l'ho eseguita io.** Il confronto ha
bisogno di due cose che questo ambiente non ha: l'inventario prodotto dallo
snapshot (S1.4, lo esegue Kimi) e una connessione a Supabase. Ho quindi scritto
lo strumento invece di indovinare il risultato:

```bash
export DATABASE_URL='postgresql://…'          # Supabase, NON il Postgres storico
python3 scripts/chiavi_storiche_attive.py postgres-legacy-inventario.md
```

Confronta gli sha256 dell'inventario con `api_keys.key_hash` e divide l'elenco
in ATTIVE e INATTIVE. **Le chiavi in chiaro non entrano mai nello script**: si
confrontano hash, non segreti.

### Piano proposto per le ATTIVE (serve l'ok del titolare)

Il principio: una chiave in chiaro in un database secondario per mesi va
considerata compromessa, ma revocarla si vede dal cliente. Quindi si sostituisce
prima e si revoca dopo — mai il contrario.

1. **FORMA per prima** (`forma-core`/`andrea`): è l'unico tenant dove un errore
   lo paghiamo noi. Emissione della nuova, aggiornamento dove è configurata,
   verifica che risponda, poi revoca della vecchia. Se qualcosa va storto, si è
   rotto un nostro strumento e non il servizio di un cliente.
2. **Finestra di sovrapposizione**: vecchia e nuova valide insieme per il tempo
   di aggiornare le configurazioni. `api_keys` regge due righe attive per lo
   stesso scope — non serve nessuna modifica al codice.
3. **Un cliente alla volta**, con avviso prima e verifica dopo: si guarda
   `key_usage`/`access_logs` per confermare che il traffico è passato sulla
   nuova, e solo allora si revoca la vecchia (`reset_chiavi.py` ha già il freno).
4. **Se una chiave attiva non ha traffico** da settimane, il caso è più semplice:
   è di fatto inattiva e si tratta come tale — ma questo lo dice il dato, non noi.

### Perché non basta aspettare

Nessuna di queste chiavi è installata presso un cliente pagante oggi (verificato
l'1/08 e scritto in `CLAUDE.md`). Il che rende la rotazione **facile adesso** e
scomoda dopo: dallo Sprint 5 entrano clienti veri, e quella finestra di
sovrapposizione diventerà una cosa da concordare con qualcuno.

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
