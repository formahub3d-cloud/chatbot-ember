# Diario dei problemi — `divina-motore`

> Regola permanente (titolare, 05-08-2026): ogni problema o incongruenza trovata
> nel codice si **aggiusta** o si **segnala** qui. Stato: **RISOLTO** o **DA
> DECIDERE**. Ogni lavoro successivo parte da questo file.
>
> Voce nuova in cima. Chi risolve una voce «DA DECIDERE» la sposta a RISOLTO
> scrivendo cosa ha fatto — non la cancella: com'era prima è metà del racconto.

---

## 2026-08-05 (notte) · RISOLTO — Tre chiavi pubblicate nel repo autenticavano davvero

**Come è saltata fuori.** Cercando le chiavi del Postgres storico si era visto
che tre delle quattro erano i segnaposto di `tenants.example.json`. Sembrava una
buona notizia — «non sono segreti, niente da ruotare». Poi la verifica di
`TENANTS_JSON` su Railway ha aggiunto il pezzo mancante: **quelle stesse tre
stringhe sono la configurazione viva dei tenant dogfood.** Erano contemporaneamente
pubbliche e valide.

La peggiore è `CHIAVE_FORMA_INTERNO`: concede `forma-core` **e `andrea`** — le
note personali, la stessa area che `learned.py` esclude a priori perché
sensibile — e in `tenants.example.json` non ha `allowed_origins`, quindi vale da
qualunque browser. Chiunque avesse letto il repo aveva in mano quella porta.

**Cosa è stato fatto.** `security.CHIAVI_SEGNAPOSTO` (gli sha256 dei tre valori,
non una quarta copia in chiaro) e `e_segnaposto()`; `tenants.get_tenant_by_key`
li rifiuta **prima di ogni backend** — il problema non è dove la chiave è
scritta, è che sia nota, quindi si chiude in un punto solo. Verso l'esterno è un
401 come per una chiave inventata: chi prova non impara niente.

Fail-closed di default, con una finestra dichiarata: `CHIAVI_SEGNAPOSTO_AMMESSE=true`
riapre per il tempo di sostituire i valori, e il motore lo scrive nel log a ogni
richiesta che la usa — così non resta accesa per dimenticanza.

**Ordine di esecuzione, importante:** questa PR **spegne i tre tenant dogfood al
primo deploy**. Prima si sostituiscono i valori in `TENANTS_JSON`
(`python -m app.manage_apikeys` genera chiavi vere), poi si mergia. Al contrario,
il dogfood resta al buio finché qualcuno non se ne accorge.

**Prove:** `tests/test_chiavi_segnaposto.py` (7 casi). Uno di questi legge
`tenants.example.json` e pretende che **ogni** chiave d'esempio sia fra quelle
rifiutate: se domani qualcuno ne aggiunge una senza registrarla, il test lo dice
prima che diventi una porta.

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

## 2026-08-05 (sera) · CHIUSO — Le chiavi storiche non aprono più niente

**Verifica eseguita** (Kimi, `scripts/chiavi_storiche_attive.py` contro Supabase,
pooler eu-west-1): **0 attive su 4**. Nessuna delle quattro è presente in
`api_keys` — né come riga revocata: proprio assenti.

Quindi **non c'è niente da ruotare**, né subito né con un piano. Le chiavi in
chiaro nel dump non aprono nessuna porta, master compresa. Il dump resta
custodito fuori dai repo per il suo valore di archivio, non perché sia pericoloso.

Resta scritto **come** ci siamo arrivati, perché è la parte riusabile:

| Hash | Nome | Cos'era |
|---|---|---|
| `a204987b…` | FORMA (interno / dogfood) | `CHIAVE_FORMA_INTERNO` — segnaposto di `tenants.example.json` |
| `78fa2bc9…` | Al Tuo Servizio (ATS) | `CHIAVE_ATS` — segnaposto |
| `f7be4c28…` | Home Restaurant Hotel | `CHIAVE_HRH` — segnaposto |
| `67c115be…` | OVY Master, scope `*` | non un segnaposto noto — **ma non attiva** |

Tre erano le stringhe letterali di `db/seed.example.sql`, pubbliche nel repo da
sempre: `ensure_seeded()` le aveva copiate nel Postgres quando quello era il
tenant store, e il fossile era fatto di esempi. La quarta era una master vera, e
per qualche ora è stata la cosa più preoccupante del progetto — poi il dato ha
detto che non è installata da nessuna parte.

**Le due lezioni, che valgono anche senza questo caso.**
1. Un segreto trovato non è un segreto in uso: prima di progettare una
   rotazione, si guarda se apre qualcosa. Qui la differenza era fra un piano in
   quattro fasi e zero lavoro.
2. Un inventario di hash **troncati** non è confrontabile con niente
   (il primo aveva 16 caratteri). Gli hash si conservano interi o non si
   conservano: `snapshot_postgres_legacy.sh` li scrive interi apposta.

---

## (storico) 2026-08-05 (sera) · Le chiavi storiche sono TRE segnaposto e UNA vera

**L'inventario è arrivato** (`divina-agenti/docs/postgres-legacy-inventario.md`,
prodotto da Kimi con S1.4). Confrontando i suoi sha256 con le stringhe d'esempio
committate nel repo, tre delle quattro combaciano:

| Hash | Nome | Cos'è davvero |
|---|---|---|
| `a204987b…` | FORMA (interno / dogfood) | `CHIAVE_FORMA_INTERNO` — **segnaposto** di `tenants.example.json` |
| `78fa2bc9…` | Al Tuo Servizio (ATS) | `CHIAVE_ATS` — **segnaposto** |
| `f7be4c28…` | Home Restaurant Hotel | `CHIAVE_HRH` — **segnaposto** |
| `67c115be…` | **OVY Master** — scope `*` | **non è un segnaposto noto** |

Le prime tre non sono segreti: sono le stringhe letterali di
`db/seed.example.sql` / `tenants.example.json`, pubbliche nel repo da sempre.
`ensure_seeded()` le ha copiate dalla sorgente statica al Postgres quando quello
era il tenant store — il fossile è fatto di esempi. **Per loro non c'è niente da
ruotare**, e il dump non è il segreto che temevamo.

**La quarta sì, ed è la peggiore delle quattro.** Non combacia con nessun
segnaposto del repo, e ha `allowed_scopes = ['*']`: è una **chiave master**, che
`ovyon.is_master()` fa passare attraverso ogni filtro RLS e ogni scope Qdrant —
tutti i clienti insieme. Fino a ieri stava in chiaro in un database secondario.

Il piano sotto vale quindi **per una chiave sola**, e la sua priorità sale:
prima di ogni altra cosa.

Attenuante (verificata nel codice, non sperata): `_reject_master_browser` in
`app/main.py` rifiuta con 403 qualunque uso di una chiave master che arrivi da
un browser. Chi l'avesse in mano dovrebbe usarla server-side — resta grave, ma
non è esposta dal widget.

**Istruzione ricevuta:** verificare quali sono ancora attive in `api_keys`;
ruotare subito le **inattive**; per le **attive** proporre un piano e lasciare
decidere il titolare (impatta i clienti).

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
