# Diario dei problemi — `divina-motore`

> Regola permanente (titolare, 05-08-2026): ogni problema o incongruenza trovata
> nel codice si **aggiusta** o si **segnala** qui. Stato: **RISOLTO** o **DA
> DECIDERE**. Ogni lavoro successivo parte da questo file.
>
> Voce nuova in cima. Chi risolve una voce «DA DECIDERE» la sposta a RISOLTO
> scrivendo cosa ha fatto — non la cancella: com'era prima è metà del racconto.

---

## 2026-08-07 · RISOLTO — Il freno avrebbe murato il dogfood al secondo messaggio

**Dove:** `app/ledger.py::mai_visto` → `mai_accreditato` (e la gemella
nell'orchestratore) · trovato **da Kimi sui dati veri, prima del merge**.

Il freno rifiuta solo con una prova, e la prova comprendeva «il tenant esiste
nel registro». L'avevo scritta come *«c'è una riga qualunque»* — e **il nome
che le avevo dato era il difetto**: `mai_visto` risponde a «è mai esistito qui
dentro», mentre la domanda che conta è «è mai stato aperto».

Un ADDEBITO prova che il cliente ha usato il prodotto, non che gli sia stata
data una dotazione. E siccome oggi in produzione i consumi si scrivono già
(tre righe di `forma-core`, tutte `misurato`) mentre gli accrediti non ancora,
al merge il dogfood sarebbe andato in 402 al messaggio dopo: saldo zero, righe
presenti, freno chiuso. Esattamente il difetto che questa prova doveva
impedire, ripresentato una riga più in là.

Adesso la prova è `direzione='accredito'`. E il test non guarda il risultato ma
la **forma della query** — un cursore finto risponde a qualunque SQL, quindi
«ha chiesto la cosa giusta» non si deduce da «ha risposto»: stessa lezione
della JOIN mancante in `_anagrafica`, questa volta applicata prima.

Vale oltre il caso: **quando un predicato ha un nome che descrive la query
invece della domanda, prima o poi qualcuno (io) risponde alla domanda
sbagliata.** `mai_visto` era leggibile e falso.

---

## 2026-08-07 · RISOLTO — Il rapporto sulla misura era cieco, e diceva «niente da misurare»

**Dove:** `scripts/rapporto_misura.py` · trovato **da Kimi in produzione**,
confrontandolo con la query manuale.

Lo script si connette col ruolo `divina`, che ha la RLS attiva: la policy
chiama `ovyon.can_read`, che legge `ovyon.allowed_tenants` dalla sessione.
Senza quel GUC la `SELECT` **non dà errore**: restituisce zero righe. Il
rapporto stampava «nessun addebito nel periodo» a registro pieno.

La riga più pericolosa era una che avevo scritto apposta per essere onesta —
«zero righe non è tutto bene, è non è passato traffico» — e che diceva la cosa
sbagliata perché il terzo caso non l'avevo previsto: *non ho potuto guardare*.
Tre esiti mai confusi vale anche per gli script, non solo per le schermate.

Fatto: `--tenant` **obbligatorio** (`'*'` = vista completa, ed è il carattere
che `ovyon.is_master()` riconosce — verificato in `db/schema.sql`, non
supposto), GUC impostati per la transazione, e il tenant guardato stampato in
testa al rapporto, così un risultato vuoto dice anche *con quali occhi* è stato
guardato.

Quinta volta in tre giorni che il difetto è **lo strumento di misura fuori
posizione**. Le prime quattro erano finte che rispondevano meglio del vero;
questa è l'opposto — il vero che risponde di meno, perché una difesa stava
funzionando. La forma è la stessa: *chi misura non era nella posizione di chi
consuma*.

---

## 2026-08-07 · DECISO — `MISTRAL_STREAM_USAGE` resta SPENTO: non serve

**Dove:** `app/config.py` (`mistral_stream_usage: bool = False`).

Misurato in produzione il 7/08 (Kimi, tre chat vere): le righe escono
`misurato` **col flag spento**. Mistral manda `usage` nell'ultimo blocco dello
stream anche senza `stream_options.include_usage`.

Il flag resta nel codice come via di fuga se un giorno smettesse di arrivare,
ma **non si accende**: accenderlo adesso vorrebbe dire cambiare una richiesta
in produzione per ottenere una cosa che già si ottiene.

Il dato che ne esce vale più della decisione: **una chat costa 2.673 · 3.007 ·
3.016 token** — circa 3k. Serve al freno, che dichiara di poter andare sotto
«al massimo di un'operazione»: adesso quel massimo ha un numero, ed è lo
**0,15% di una dotazione mensile**. Lo scoperto accettato non è più una
promessa qualitativa.

---

## 2026-08-07 · DA DECIDERE — Il freno si può accecare, e fallisce aperto

**Dove:** `app/ledger.py::_sessione` → `rls.set_grants(cur, allowed_scopes)`.

Il registro filtra per `tenant_code` (da `branding.tenant_code`), ma la RLS
filtra per gli **scope** della chiave. Oggi combaciano — una chiave cliente
nasce con `tenants: [tenant_code]` e la dogfood ha `forma-core` fra gli scope —
ma sono due cose diverse, e nessuno lo impone.

Se un giorno divergessero, la `SELECT` del saldo tornerebbe vuota: il freno
leggerebbe zero, `mai_accreditato` direbbe «mai aperto», e passerebbe tutto —
in silenzio. Fallisce nella direzione giusta (aperto, non chiuso), ma **senza
dirlo**, che è la parte che non mi piace.

Non l'ho risolto adesso perché le strade costano diverso: (a) un controllo
all'avvio che confronta `branding.tenant_code` con `allowed_scopes` di ogni
chiave e lo dichiara in `/admin/status`; (b) far scrivere al freno una riga di
log quando il saldo è vuoto E il tenant non è fra gli scope — cheap, locale,
ma è una spia dentro un percorso caldo. Propendo per (a). La scrittura, va
detto, il difetto lo mostrerebbe comunque: l'INSERT verrebbe rifiutato dal
`with check` e finirebbe nei log.

---

## 2026-08-07 · RISOLTO — La chat senza streaming non contava niente

**Dove:** `app/main.py` (`do_chat`), `app/rag.py` · trovato costruendo il freno,
chiedendomi su quale saldo scendesse il credito di chi non usa la console.

`stream` è **`false` di default** nel corpo di `/chat`. Il pannello e il widget
chiedono lo streaming, quindi la riga del registro si scriveva sempre e il buco
non si vedeva; ma il connettore MCP, uno script, un `curl` — e chiunque
integrasse il motore leggendo la documentazione — passavano dal percorso
non-stream, che **non scriveva niente**. Conseguenza doppia: consumo non
contato, e un freno sul saldo che per quei tenant non sarebbe mai scattato,
perché quel saldo non scendeva mai.

Adesso anche `rag.answer` accetta il misuratore, e `do_chat` scrive la riga
dopo. Con una distinzione che non è formale: **una risposta che non passa dal
modello** (un saluto, un chiarimento, un «lascia stare») **costa zero per
davvero**, e si scrive `Uso(0, 0)` — non `None`. `None` finisce nel registro
come `ignoto`, e sono proprio quelle righe che dovranno dirci se il consumo non
misurato è un problema: contarci dentro le risposte gratuite vorrebbe dire
inseguire un numero fatto da noi. Il conteggio delle chiamate vive dentro
`providers.chat_stream`/`UsoInStream.somma_uso`, cioè accanto alla chiamata
vera: da un'altra parte, un giorno, si dimenticherebbe.

**Effetto collaterale voluto:** `rag` non importa più `chat`, solo
`chat_con_uso` (che era già l'unica implementazione — `chat()` era il suo
`[0]`). Una cucitura sola: i test agganciavano `rag.chat`, che dopo questa
modifica nessuna richiesta vera avrebbe più attraversato. Trenta patch di test
spostate; una che restasse indietro fallisce forte (`AttributeError`), non in
silenzio.

---

## 2026-08-07 · RISOLTO — Il finto di `addebita` restituiva `None` e nascondeva il ramo d'errore

**Dove:** `tests/test_chat_ledger.py`, fixture `chat_finta`.

Il finto era `lambda …: scritte.append(…)`, cioè `None`. Da S5.1c/2 chi chiama
legge `esito["righe"]` per scalare il saldo tenuto in mente: col `None` la
chiamata sollevava, l'eccezione finiva nel `try` di difesa e i sei test
restavano **verdi provando il percorso dell'errore**. Adesso il finto ha la
forma vera del ritorno.

Terza volta in tre giorni che il problema è lo strumento di misura fuori
posizione (il `TestClient` che leggeva header CORS, la fixture col tenant
dell'altro servizio, e ora questo). Il segno è sempre lo stesso: **il test non
fallisce, si sposta**.

---

## 2026-08-06 · RISOLTO — «tenant=None»: la stessa parola per due cose diverse

**Dove:** `app/ledger.py` (mio, di stamattina) · trovato **in produzione** da
Kimi con due chat di prova, prima di accendere la misurazione.

```
ERROR ember.ledger: registro token non scritto (tenant=None op=chat token=2529)
```

**Cosa avevo sbagliato.** Nel motore «tenant» è una **chiave API**: scope,
origini ammesse, `branding`, quota. Nell'orchestratore è una **riga di
`tenants`**: `tenant_id`, `org_code`, `code`. Ho scritto il registro del motore
usando la forma dell'orchestratore — `tenant["code"]`, `tenant["tenant_id"]` —
e in produzione `code` non esiste: da lì il `None` nel log e il `KeyError`
inghiottito dal `try` generico.

**Perché i test non l'hanno visto: erano sbagliati con me.** Avevo scritto la
fixture `TENANT` con la forma dell'orchestratore, così il test confermava la mia
idea invece del prodotto. È la stessa famiglia del `TestClient` che leggeva gli
header CORS e del `set role` annullato dal rollback: **lo strumento di misura
che non sta nella posizione del consumatore vero.** Tre volte in due giorni, e
tutte e tre trovate fuori dalla suite.

Fatto:

- il codice si legge da **`branding.tenant_code`**, che è dove lo scrive
  `POST /admin/tenants` quando FORMA conia la chiave di un cliente;
- **gli scope non diventano un tenant.** La chiave dogfood ne ha due
  (`forma-core`, `andrea`): sceglierne uno vorrebbe dire attribuire il consumo a
  caso, e meglio non scrivere che scrivere sul cliente sbagliato;
- senza codice **non si prova nemmeno**, e lo si dichiara una volta per chiave
  con dentro gli scope che aveva: prima si provava e si falliva dentro, con un
  errore che non diceva qual era il problema;
- `tenant_id` e `org_code` si risolvono dall'anagrafica (`select … from tenants
  where code=…`), e un codice che il database non conosce non si scrive: quelle
  colonne sono NOT NULL con una FK, e una riga con un'identità inventata è
  peggio di una riga mancante;
- la fixture dei test adesso ha la forma vera, e cinque prove nuove coprono i
  casi (chiave senza codice, scope che non diventano tenant, anagrafica assente).

---

## 2026-08-06 · DA DECIDERE — Il motore parla con Supabase da PRIVILEGIATO

**Dove:** `app/tenants.py::_conn()` (`settings.database_url`) ·
`SETUP-PRODUZIONE.md` §35 · trovato prima di scrivere il ledger nel motore
(S5.2), come promesso.

**Cosa ho verificato.** Il motore si connette con la `DATABASE_URL` che il
runbook fa raccogliere dal pannello Supabase — la *connection string* del
progetto, non un ruolo applicativo. La prova che non è il ruolo `divina` sta nel
codice stesso: `init_and_seed()` esegue `CREATE TABLE IF NOT EXISTS tenants`, e
`divina` non ha `CREATE` (db/002 gli dà `usage` sugli schemi e `select/insert`
sulle tabelle, nient'altro).

**Perché conta adesso e non prima.** Le due garanzie che Kimi ha appena
verificato su `token_ledger` — `UPDATE` e `DELETE` negati, RLS che isola i
tenant — **sono grant sul ruolo `divina`**. Il proprietario del database le
scavalca entrambe per costruzione. Se il motore scrivesse il registro con la
connessione di oggi:

- l'append-only smetterebbe di essere vero **per metà del traffico** (la chat,
  che è il consumo grosso) e resterebbe vero per l'orchestratore: la stessa
  tabella con due regole diverse a seconda di chi scrive;
- un errore nel calcolo del tenant scriverebbe la riga sul cliente sbagliato
  **senza che il database lo fermi** — cioè il difetto di S1.3 in una tabella
  che diventa una fattura.

Nessuna delle due si vedrebbe in un test: i test girano su un cursore finto, e
in produzione l'INSERT riuscirebbe. È il difetto che passa la suite e muore in
bolletta.

**Le due strade.**

1. **Il motore usa il ruolo `divina` per il registro** — una seconda variabile
   (`DATABASE_URL_LEDGER`) usata SOLO dal modulo del ledger, con la connessione
   privilegiata che resta per tutto il resto. Nessun ruolo nuovo da creare, i
   grant sono già quelli verificati, e la superficie del cambiamento è un
   modulo. È quella che consiglio.
2. **Il motore non scrive**: restituisce l'uso e lo scrive l'orchestratore. La
   ragione per cui `openapi.yaml` aveva scelto la scrittura diretta era «niente
   hop di rete nel percorso della risposta» — ma l'uso della chat si conosce
   **a stream finito**, quando la risposta è già arrivata all'utente, quindi
   quella ragione qui non si applica. Costa un giro di rete in più e un
   contratto nuovo fra i due servizi.

Non ho scritto il ledger nel motore prima di questa decisione, perché la
decisione È quale connessione scrive.

---

## 2026-08-05 (notte) · CORREZIONE MIA — «porta aperta oggi» era esagerato

Avevo scritto che le tre chiavi segnaposto erano «una porta aperta oggi».
Verificando la produzione, Kimi ha trovato il pezzo che mi mancava: il motore
gira con `GRANTS_BACKEND=supabase`, quindi `get_tenant_by_key` risolve da
`api_keys` per hash — e le tre segnaposto in `api_keys` **non c'erano** (0/4,
coerente con `chiavi_storiche_attive.py`). Per `/chat` erano già morte.

Il codice conferma il perché: `resolve_key_apikeys` che non trova la chiave
ritorna `None` e la richiesta finisce lì; si ripiega su `TENANTS_JSON` **solo se
la chiamata solleva**, cioè se Supabase è irraggiungibile.

Quindi la porta esisteva, ma stretta: **durante un guasto del database**. Che è
poi la stessa famiglia del fail-open già annotato più sotto — quando il DB non
risponde il sistema diventa più permissivo, non meno. Vale la pena chiuderla lo
stesso (una chiave nota non deve autenticare in nessuno scenario), ma la
gravità era quella di un caso degradato, non del percorso normale.

Lezione, per me più che per il codice: avevo dedotto la conseguenza («autentica
in produzione») da due fatti veri («è nel repo» + «è in TENANTS_JSON») senza
verificare il terzo, cioè quale sorgente la produzione usa davvero. Due fatti
veri non fanno una conclusione vera.

---

## 2026-08-05 (notte) · RISOLTO — Il ramo del vault, dichiarato

Segnalazione OPS: `VAULT_GIT_REF` non è mai stata impostata sul motore.
**Nessuna azione necessaria sull'env**: il default nel codice è già `main`
(`config.vault_git_ref`), messo lì dal fix A0 proprio perché il default di
questo repo vault è `feature/wave-01` e la produzione aveva fotografato il ramo
sbagliato. L'ingest del ripuntamento conferma: `vault_commit 64a7bceb9127`, che
è la testa di `main`.

Due bordi chiusi lo stesso, perché erano gli unici modi di riaprire quel difetto:

1. **Un ramo vuoto non arriva a git.** `VAULT_GIT_REF=` su Railway avrebbe
   passato una stringa vuota a `git fetch`, e il fallimento sarebbe arrivato
   travestito da «clone non riuscito» — lontano dalla causa. Ora
   `config.ramo_vault()` normalizza: vuoto → `main`.
2. **`vault_info()` dichiara il RAMO**, non solo il commit. Il difetto originale
   non era «un commit vecchio», era «il branch sbagliato»: due sha sembrano
   uguali finché non si sa da dove vengono. Ora `/ingest` e `/admin/brain`
   dicono anche `vault_ref`.

Si dichiara il ramo *chiesto*, non quello del clone: uno shallow clone resta in
HEAD staccato e chiedere al git locale «su che branch sei» risponderebbe «HEAD».

**Prove:** `tests/test_a0_vault_stantio.py` (2 casi nuovi).

---

## 2026-08-05 (notte) · CHIUSO — S1.5b, il motore è sul Qdrant interno

Eseguita da Kimi con la sequenza (b): pre-check del vault (commit < 48h, quindi
la guardia anti-stantio non blocca), cambio env, redeploy, `POST /ingest`,
verifica. Esito: **105 note · 389 chunk · 428 link**, commit `64a7bceb9127`.

La verifica che vale più delle altre non è il conteggio dell'ingest ma la
**parità indipendente**: un clone locale del vault contato a mano con le regole
di `is_note_included` dà 105 = 105. Un ingest che dichiara un numero è una
misura di sé stesso; due conteggi diversi che coincidono sono una prova.

Rollback intatto: il Qdrant Cloud esterno non è stato toccato. La sua chiusura è
una decisione del titolare (costi), non un passo tecnico rimasto.

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

**Ordine di esecuzione** — ~~questa PR spegne i tre tenant dogfood al primo
deploy~~ **superato**: le tre chiavi sono state sostituite da Kimi in entrambi
gli store (TENANTS_JSON e `api_keys`) **prima** del merge, con lo stesso formato
e gli stessi scope. Il merge non spegne più niente. La precauzione resta valida
come regola generale: un controllo che rifiuta credenziali va sempre dopo la
loro sostituzione, mai prima.

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
