# V9 · Riempire il cervello di un cliente senza chiederglielo

> 2 agosto 2026, pomeriggio. Nasce da una cosa vista in produzione mezz'ora
> prima, non da un piano.

Andrea dichiara una preferenza in chat — *«rispondimi sempre in modo molto
breve»* — e la pagina «Cosa so di te» dice ancora **0 cose**. Non era un difetto:
mancava `tenant_memory` su Supabase. Il blocco B1 del V7 («il motore dichiara
cosa gli manca») si è ripagato in una chiamata sola. Ma ha mostrato anche il suo
limite, ed è il primo blocco di questo giro.

---

## A · Il degrado dichiarato dove si vede

`app/degrado.py` · console: `boxDegrado()` e `vuotoOnesto()`

La pagina diceva *«Non so ancora niente di te»* mentre la verità era *«non posso
ricordare niente, mi manca la tabella»*. Chi apre una schermata non va a leggere
lo stato tecnico: legge quella frase e conclude che la funzione non serve a
niente. **Una funzione spenta che sembra inutile non chiede di essere riparata.**

`dbcheck` aveva già la frase giusta per ogni tabella. Mancava il tubo.

### Un modulo, non tre `if`

I casi trovati erano tre e sarebbero diventati cinque il mese prossimo. E
soprattutto la dipendenza non è sempre una tabella: le voci degli agenti
dipendono da variabili d'ambiente, la lettura del sito di un cliente da una
chiave. Qui la forma è una sola.

Il PERCHÉ delle tabelle **non si riscrive**: si legge da `dbcheck.ATTESE`. Due
copie della stessa frase divergono, e quella sbagliata è sempre quella che legge
l'utente — c'è un test che lo impone.

### Tre esiti, mai due

| | |
|---|---|
| `acceso` | tutto quello che serve c'è, e non si mostra niente |
| `spento` | manca qualcosa: si dice cosa smette di funzionare e come si accende |
| `non-so` | non si è potuto guardare — che non è nessuno dei due |

Dire «non lo so» come se fosse «acceso» è il modo esatto in cui nasce un pannello
che mente. È la stessa regola di `dbcheck`, non una nuova.

### Due dettagli che valgono la pena

- Al **cliente** la riga tecnica non si mostra: non è lui a dover impostare una
  variabile su Railway. Sa cosa non funziona, non come si ripara.
- `vuotoOnesto()` impedisce a uno stato vuoto di fingersi vuoto quando invece è
  spento. Era letteralmente il difetto.
- Quando le ragioni sono tante e uguali, la frase è **una**: «Dante, Virgilio e
  Beatrice parlano ancora con la voce di Divina». La versione letterale è
  tecnicamente giusta e nessuno la legge fino in fondo.

---

## B · La KB di un cliente nasce dal suo sito

`app/sitokb.py` · console: Clienti → «Proponi dal sito»

Le KB dei cinque clienti stanno fra le 61 e le 77 righe. Il motivo non è tecnico:
riempirle è lavoro manuale che dipende dal cliente, e per chiederglielo
bisognerebbe chiedere un favore **prima** di aver mostrato il valore.

Il ribaltamento: si prende l'indirizzo del sito, se ne ricava una bozza, e poi si
apre il pannello del cliente e gli si chiede *«cosa è sbagliato qui?»*.
Correggere è cento volte più facile che compilare.

### Le tre regole, in codice

1. **Ogni pezzo porta la sua fonte** — quale URL, quale frase, verificata
   letteralmente con `learned._cita_vera` (la stessa funzione, non una copia).
   *Caso deciso e testato:* se il modello sbaglia pagina ma cita bene, si tiene
   la frase e si corregge l'indirizzo. Ha detto una cosa vera con la fonte
   sbagliata; pubblicare un URL che non contiene la frase sarebbe la bugia
   peggiore.
2. **Niente persone.** Il controllo sui nomi vale in **ogni** sezione — e il
   primo tentativo era sbagliato: l'avevo messo solo nei contatti, ma
   `redact_pii` copre email, telefoni e IBAN, non «Mario Rossi — direttore
   vendite», che è esattamente ciò che c'è su ogni pagina «chi siamo». Sarebbe
   stato il buco più grande del blocco.
   La deroga riguarda solo i **recapiti**: nella sezione contatti un `info@` e un
   indirizzo passano, perché un bot che non sa dire dove sei non serve a niente.
3. **Nessuna scrittura automatica.** Le voci entrano in coda e si approvano una
   per una, anche quando sono dodici. Approvare scrive la nota **marcata «NON
   verificato»**, e qui la marcatura pesa più che altrove: quel testo il cliente
   l'ha scritto per i suoi visitatori, non per noi.

### Perché legge Tavily e non il motore

Un motore che scarica un URL deciso da chi fa la richiesta è un ponte verso la
rete interna. Delegando, l'unica cosa che entra è testo. Due passaggi: si
scoprono le pagine interne con una ricerca ristretta al dominio, poi si estrae il
testo; senza estrazione si ripiega sugli snippet — più corti, ma veri, e la
citazione si verifica lo stesso contro ciò che si è letto.

### Ogni «zero» dice il suo perché

Senza chiave · sito illeggibile · sito quasi vuoto (col numero di caratteri) ·
zero voci dopo i controlli. Sono quattro esiti diversi, e una lista vuota muta
farebbe concludere che il cliente non ha un sito.

---

## C · Le capacità si raggiungono dalla conversazione

`app/agents_bridge.py` — `catalogo()`, `vettori()`, `trova()`

Task aperta dal 31 luglio. Il V7 aveva messo il riconoscitore **nella console**,
leggendo `/agents`: la scelta di non duplicare il catalogo era giusta e resta. Ma
aveva due difetti che si vedono solo adesso.

**Esisteva solo lì.** Nel widget sul sito di un cliente non c'era, e a voce non
c'era affatto — un chip non si clicca mentre si parla. Se la capacità non entra
nella **frase**, per chi parla non esiste.

**E il metodo non poteva funzionare.** Il criterio è «una capacità esiste quando
qualcuno può usarla senza sapere come si chiama». Ma

> «cerca chi vende stampa 3D a Benevento»
> «trova e qualifica potenziali clienti, studia il mercato attorno»

hanno **una parola in comune su otto**. Contare le parole vuol dire chiedere
all'utente di indovinare il vocabolario della skill: il nome, scritto peggio.
C'è un test che lo dimostra prima di correggerlo.

La correzione usa una cosa che c'era già: **il vettore della domanda**, che il
retrieval calcola comunque per cercare nel vault. Adesso si calcola una volta e
serve a due cose. Costo per messaggio: zero. Le descrizioni delle skill si
vettorizzano una volta ogni dieci minuti, insieme al catalogo — che continua a
non essere duplicato da nessuna parte.

Senza embedding si ripiega sulle parole: peggio, ma non muto. E **se il vettore
ha guardato e ha detto di no, non si ripiega**: cercare un sì finché non arriva è
il modo di trasformare un suggerimento in rumore.

`capTrova`/`capCatalogo` spariscono dalla console. Due matcher divergono, e
quello sbagliato è sempre quello che vede l'utente — il guardiano fallisce se
tornano.

**Il vincolo non si allenta.** Il prompt dice di OFFRIRE e vieta esplicitamente
di dire che è fatto, di promettere un risultato o di produrre il lavoro. Ciò che
ha effetto fuori nasce `in-approvazione` e col livello 3 spento non si accoda:
porta principale e porta di servizio restano chiuse dal V5c.

---

## D · La conversazione che dura

`app/riassunti.py` · `db/conversation_summary.sql`

Un riassunto compresso per conversazione — *epoch summaries*, l'unica cosa
architetturalmente interessante di Zoey. Tenere tutti i turni non scala e
moltiplica i dati personali conservati: comprimere è insieme la scelta tecnica
migliore e quella che tiene meno roba in giro.

**Si scrive una volta, a conversazione finita.** È questo che lo rende
compatibile con la voce: la chiamata al modello avviene quando nessuno sta
aspettando una risposta, e i 55 ms di prima sillaba non si toccano.

Chi dice che è finita: il client (`POST /chat/chiudi`), perché è l'unico che lo
sa. **Non c'è una spazzatura periodica che comprima i fili scaduti, e non fingo
che ci sia**: servirebbe un lavoro schedulato e questo motore non ne ha. Un filo
che muore senza che nessuno chiuda resta non compresso — buco dichiarato.

### I due limiti

**Non allarga i permessi.** Stesso vincolo del filo e stesso test: un riassunto
che nomina `andrea-aloia` non dà a un tenant ATS un solo scope in più. La tabella
non ha nemmeno una colonna `scope` — metterla sarebbe stato il primo passo per
usarla come filtro.

**È un dato personale.** Retention 30 giorni applicata **anche in lettura**: una
riga scaduta non compare nemmeno se la pulizia non è passata — è la differenza
fra una promessa e un comportamento. E il «Dimentica» ci arriva: i promemoria
stanno nella stessa pagina «Cosa so di te», ognuno col suo bottone. Se non ci
arrivasse, l'art. 17 sarebbe coperto a metà, e mezza copertura su un obbligo di
legge è peggio di nessuna promessa.

---

## Le migrazioni (nessuna è un prerequisito)

| File | Senza, cosa succede |
|---|---|
| `db/conversation_summary.sql` | la conversazione non dura oltre la sessione: i promemoria si perdono al redeploy |

Le altre quattro sono quelle del V8, ancora da applicare. `app/dbcheck.py` le
dichiara tutte, e adesso ogni schermata dichiara la propria.
