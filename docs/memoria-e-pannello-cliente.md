# V8 · Quello che si vede al primo incontro

> 2 agosto 2026. Nasce da un'analisi condotta **dentro Zoey OS** installato sul
> Mac di Andrea, prima della disdetta dell'abbonamento.

La frase da cui nasce tutto:

> **Divina è il prodotto che si vende bene al secondo incontro. Manca quello che
> si vende al primo.**

Le cose in cui Divina è avanti — permessi server-side, fonti citate, conferma
umana, isolamento fra clienti, conformità europea — si **spiegano in dieci
minuti a un cliente diffidente**. Le cose in cui Zoey è avanti si **vedono in
trenta secondi di demo**. Questo giro chiude il secondo gruppo senza toccare il
primo.

---

## A · «Cosa so di te» — la memoria visibile

`app/memoria.py` · `db/tenant_memory.sql` · console: Squadra → «Cosa so di te»

La cosa migliore vista in Zoey, senza i suoi due difetti.

### Niente percentuale, e non è una mancanza

In Zoey **tutte le memorie sono al 70%**: un numero costante travestito da
misura. Gli unici criteri veri qui disponibili sono due, e sono già onesti così
come sono:

| Cosa si mostra | Perché è un criterio |
|---|---|
| `conferme` — quante volte l'hai ridetto | è un conteggio, non una stima |
| `citazione` — la frase da cui viene | è la fonte, verificabile a occhio |

Una percentuale calcolata da questi due sarebbe una formula inventata sopra due
dati veri: peggio dei dati veri. Il guardiano headless fallisce se in quella
pagina ricompare un simbolo di percentuale — è la protezione che impedisce di
«migliorarla» per distrazione fra sei mesi.

### La memoria si USA

Il difetto più istruttivo di Zoey: fra le sue memorie c'è *«Andrea prefers
Italian language for business communication»*, al 70%, e il riassunto finale
della stessa conversazione è **in inglese**. Ricorda e non se ne serve.

Qui una memoria può avere una **chiave** fra quelle che il motore sa applicare
(`lingua`, `lunghezza`). Le voci con una chiave diventano comportamento:
`main.do_chat` legge `memoria.preferenze()` PRIMA di rispondere, e la lingua
ricordata batte il default del tenant. Non batte una lingua chiesta nella
richiesta: **un'istruzione di adesso vale più di una di ieri**, sempre.

Le voci senza chiave entrano nel prompt come contesto su chi sta parlando, con
due cautele scritte esplicitamente: non sono CONTENUTO (non si citano come
fonti) e non allargano niente (una preferenza non è un permesso).

Il test `test_la_lingua_ricordata_cambia_la_risposta` diventa rosso se questo
smette di succedere. È il test che vale più della funzione.

### Dimenticare cancella davvero

Il progetto ha la regola «nessun DELETE: si archivia». Qui c'è una deroga
deliberata: l'art. 17 GDPR non si soddisfa con `status='archiviato'` e il testo
ancora dentro. `dimentica()` **svuota** fatto, citazione, valore e chiave, e
lascia la lapide — id, quando, chi. Resta che qualcosa è stato dimenticato, non
che cosa. È l'unico punto del sistema dove un testo sparisce.

### Come si forma una memoria

Due strade, entrambe visibili:

1. **Detta in chat.** Un riconoscitore a regole (nessuna chiamata LLM: gira su
   ogni messaggio, anche a voce, dove il budget è la prima sillaba a 55 ms)
   individua le preferenze dichiarate esplicitamente — «parlami in italiano»,
   «rispondi breve». Vale **già da quella risposta**, e la console lo dice nella
   bolla col bottone per dimenticarlo. Una memoria che si forma di nascosto è la
   cosa che rende sgradevoli questi prodotti.
2. **Scritta a mano** nella pagina.

Non è la stessa cosa di `learned.py` (le note dalle conversazioni), che resta
com'era: coda, citazione, conferma umana. Lì si estrae conoscenza dal parlato;
qui si registra un'istruzione che la persona ha appena dato. Se il messaggio
contiene dati personali, ovunque, non si registra niente: senza citazione non
c'è fonte, e una citazione da redigere non è una citazione.

---

## B · Il pannello del cliente

`app/clientkb.py` · `db/client_report.sql` · `db/tenant_flags_buchi.sql`

Nel sistema esistono tre tipi di persone e ne erano implementate due:

| Chi | Vede | Scrive |
|---|---|---|
| **Andrea** (owner) | tutto il cervello | sì, con approvazione |
| **Il cliente** — ATS come azienda | ⚠️ non esisteva | — |
| **I visitatori del sito di ATS** | niente, solo risposte | mai |

Il cliente aveva le credenziali e una sola porta: la chat. Poteva **parlare** col
proprio cervello e non poteva **guardarlo**.

### Le tre porte, e non una di più

- **`/client/kb`** — «ecco le cose che sappiamo di voi», con la data di
  aggiornamento. È la frase che vende il prodotto al primo incontro.
- **`/client/segnala`** — «questa è sbagliata». Una **proposta** nella coda
  dell'owner, mai una scrittura nel vault. Il cliente ottiene di essere ascoltato
  su ciò che lo riguarda senza che nessuno gli dia una penna sul cervello di
  qualcun altro. Le segnalazioni compaiono in «Miglioramenti» marcate *Dal
  cliente* e si chiudono col nome di chi risponde: una segnalazione che sparisce
  senza risposta insegna a non segnalare più.
- **`/client/buchi`** — le domande rimaste senza risposta sui suoi dati.

### Il punto delicato, dichiarato

Le domande dei buchi **le hanno scritte i suoi utenti finali**. Sono dati dei
clienti del cliente, e il motore gira ancora in US West. Perciò la pagina esiste
ma è dietro `flags.buchi`, spenta di default, terza della famiglia
`liv3`/`libera`: sul record, server-side, accesa da una persona col suo nome.

Da spenta la pagina **dice perché**. Una lista vuota muta direbbe «nessun buco»
— la cosa più sbagliata da far credere a un cliente il cui bot non sa rispondere.

Le domande sono già redatte a monte, ma **la redazione non è il consenso**.

### Perché prima della raccolta automatica

Le KB dei clienti stanno fra le 61 e le 77 righe: scheletri, perché in modalità
cliente il pulsante «salva nel cervello» è nascosto — scelta giusta — e quindi
crescono solo se le scrive Andrea a mano. Dieci minuti del cliente che guarda e
corregge valgono più di cento conversazioni raccolte da sole; e quando la
raccolta si accenderà, sarà lui ad approvare sulla sua roba. Il problema dei
dati dei suoi utenti diventa un accordo invece che una sorpresa.

### Il confine

Niente qui prende lo scope dalla richiesta: arriva sempre dai grant della
sessione cliente, letti server-side dal cookie. C'è un test che prova che
passare `tenant` nel corpo non serve a niente.

---

## C · Le tre cose che si vedono in trenta secondi

- **Una voce per agente** (`ELEVENLABS_VOICE_ID_DANTE` e compagni). Al server va
  il **nome** dell'agente, mai un voice_id: un browser non deve poter scegliere
  quale voce far pagare. Variabile vuota = voce di Divina, quindi chi non le
  imposta non sente nessun cambio. La Diagnostica dice quali agenti parlano
  ancora con la gola di Divina.
- **La delega dentro il filo**: `↗ affido a Dante` / `✓ Dante ha finito`, righe
  di sistema — niente avatar, niente bolla, perché devono leggersi come
  annotazioni e non come un altro interlocutore. La Regia live resta dov'era.
- **Il risultato è una scheda con un nome**, e solo se è davvero un oggetto:
  incorniciare una risposta di due righe la farebbe sembrare più di quel che è.

---

## D1 · Il menu che si illuminava e non cambiava pagina

Il sospetto nel prompt era il disegno del grafo che tiene occupato il thread.
**Non era quello** — misurato, non dedotto, con lo stesso metodo che il 31/07 ha
evitato di dare la colpa a iOS.

Ogni vista è `async`: scrive lo scheletro, aspetta la rete, poi **riscrive**
`#content`. Barra e titolo invece cambiano subito, dentro `route()`. Se la vista
che lasci è più lenta di quella che apri, l'ordine di arrivo si inverte: la nuova
disegna, la vecchia arriva dopo e le passa sopra. Barra e titolo sulla nuova,
contenuto della vecchia — il sintomo esatto. Al secondo clic le risposte sono in
cache e la corsa non si vede più: ecco i «due o tre clic».

La regola adesso: **solo il giro di navigazione corrente può dipingere.**
`route()` incrementa `_giro` e lo passa alla vista; la vista, prima di scrivere,
controlla di essere ancora quella richiesta e altrimenti si ferma — senza
scrivere e senza agganciare i suoi gestori a una pagina che non è più la sua
(una vista scaduta che riaggancia i bottoni li lascerebbe morti: sarebbe stato
lo stesso difetto, travestito).

Il numero del giro si incrementa **dopo** il ritorno anticipato di `route()`
(«apri la chat, vista invariata»): incrementarlo prima annullava un caricamento
in corso e lasciava la vista a scheletro per sempre.

Nel guardiano c'è la riproduzione, con la rete rallentata a mano.

---

## Le migrazioni (nessuna è un prerequisito)

| File | Senza, cosa succede |
|---|---|
| `db/tenant_memory.sql` | «Cosa so di te» vive in RAM: le preferenze si perdono al redeploy e il DIMENTICA cancella una cosa che sarebbe sparita da sola |
| `db/client_report.sql` | le segnalazioni del cliente si perdono al redeploy invece di arrivare nella coda |
| `db/tenant_flags_buchi.sql` | la vista dei buchi non si può accendere per nessun cliente (resta spenta, che è il freno) |

`app/dbcheck.py` le dichiara mancanti e dice cosa smette di funzionare, con la
riga `[db]` all'avvio e in Diagnostica.
