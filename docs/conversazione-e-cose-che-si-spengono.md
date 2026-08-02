# V10 · La conversazione, e due cose che si spengono da sole

> 2 agosto 2026, sera. Due blocchi su tre nascono da cose viste in produzione oggi
> pomeriggio, non da un piano. Il terzo è l'area che non si muoveva da quattro giorni.

---

## A · Il clone del vault è una dipendenza, come le tabelle

`app/degrado.py` — `vault()` e `clone_del_vault()` · `app/ingest.py` — `procura_clone()`

Su Railway ogni redeploy fa un container nuovo, e la cartella del vault non c'è.
`vault_info()` torna `{}`, l'allarme sui commit ha bisogno di **due** valori per
confrontarli, e **si spegne da solo**. Scende sulle ore — e dopo un riavvio le ore
sono sempre poche.

Alle 17:40 lo stato era questo:

```
vault:          {}
ingest_commit:  8ed778cbd45b   ← il commit del V8
allarme:        spento
quadro:         6,9            ← il punteggio vecchio, mostrato come se fosse quello nuovo
```

Il V9 era mergiato da venti minuti. **Una fascia che sparisce si legge come «va tutto
bene»**, e nessuno se ne sarebbe accorto senza confrontare i due commit a mano. Non è un
caso raro: succede a ogni configurazione, e quel giorno le variabili di Railway sono state
toccate cinque volte.

### A1 · Il clone entra nel registro

`dbcheck` non può vederlo — non è una tabella — quindi ha un accertamento suo, con gli
stessi tre esiti di tutto il resto più uno di configurazione:

| | |
|---|---|
| `c'è` | il commit si legge, l'allarme può confrontare |
| `manca` | container nuovo: *«non si può confrontare: il cervello non ha ancora letto il vault dopo il riavvio»* |
| `non-configurato` | nessun `VAULT_GIT_URL`: si legge una cartella locale, e non esiste un commit da confrontare |
| `non-so` | l'accertamento stesso non è riuscito |

La frase dice **cosa non si può fare**, non cosa manca: «manca il clone» è il rimedio, e
sta nella riga tecnica. E il registro somma il clone con `ingest_meta` in **una frase
sola** — chi guarda non deve leggere due avvisi per capire una cosa.

Nella pagina del Cervello la vecchia riga tirava a indovinare la causa («serve
`ingest_meta` e una ingest col motore aggiornato»); adesso la causa la dice il registro,
che ha guardato.

### A2 · Il clone si riprende da solo — e NON si reindicizza

Un allarme che si spegne a ogni deploy e che qualcuno deve riaccendere a mano è un allarme
che prima o poi non riaccende nessuno. All'avvio, in un thread, il motore si procura il
clone. **Reindicizzare non è compreso, ed è una scelta:**

1. **Non è l'indice ad essere sparito.** Qdrant sta fuori dal container e sopravvive al
   redeploy: il cervello sa ancora tutto quello che sapeva. È sparito il *metro*. Una
   ingest completa ricalcolerebbe gli embedding di ogni nota per riscrivere lo stesso
   indice — si pagherebbe il modello per arrivare dov'eravamo.
2. **Railway riavvia i container anche senza deploy** (OOM, healthcheck che sfarfalla).
   Legare una reindicizzazione all'avvio trasforma un ciclo di riavvii in un ciclo di
   reindicizzazioni contro l'API degli embedding: un guasto piccolo in un conto grande.
3. **Ciò che si era rotto è il CONFRONTO**, e al confronto basta il clone: un git shallow,
   qualche secondo, zero chiamate al modello, zero scritture. Ripreso quello, l'allarme
   dice da solo «il vault è avanti, lancia una ingest» — che resta una decisione di una
   persona, visibile, invece di un lavoro che parte da sé mentre nessuno guarda.

Il degrado guarda il **risultato**, non il tentativo: non c'è modo che questa funzione
dica «fatto» mentre il clone non c'è. E un lock serializza le operazioni git, perché
`_fresh_clone_swap` rinomina la cartella e due git in parallelo sono il modo più veloce di
ritrovarsi con mezzo vault.

---

## B · La voce dell'agente: misurata, non indovinata

Andrea: *«gli agenti parlano ancora tutti con la stessa voce»*. Le due ipotesi erano che
la lettura fosse spenta di default, oppure che la chat scritta non chiamasse `speak()`.
Sono difetti diversi, quindi prima si misura.

Aperta la console senza testa, agganciati `speak()` e il motore vocale, scelto Dante,
mandato un messaggio:

```
state.tts:  false                    ← la lettura nasce spenta
speak():    {agente: "dante", tts: false}   ← chiamata, con l'agente GIUSTO
setAgente:  (nessuna)                ← esce alla prima riga: `if(!state.tts&&!force)return`
/voice/tts: 0 richieste

… clic su #chatTts, stesso messaggio …
setAgente:  "dante"
/voice/tts: 1 richiesta, corpo {"text": …, "agente": "dante"}
```

**La tubatura era giusta da cima a fondo.** Nessuna voce partiva perché la lettura nasce
spenta, e l'unico comando è un'icona il cui unico segno è un `title` — invisibile su un
telefono, che è dove Divina si mostra. È il motivo per cui ventidue secondi di attesa
avevano prodotto zero chiamate.

**Una funzione che c'è ma non parte si scambia per una funzione rotta**, e sono due
riparazioni diversissime. Quindi:

- lo stato della lettura sta in un attributo (`data-tts`), non solo nel disegno
  dell'icona: lo legge il guardiano, e chi usa uno screen reader anche;
- in **Squadra** — dove uno viene a chiedersi perché suonano tutti uguali — a lettura
  spenta c'è scritto: *«le voci sono impostate, ma la lettura ad alta voce è spenta: ogni
  agente suona uguale perché non suona affatto»*, con il bottone per accenderla.

Il guardiano adesso sorveglia le due metà: che la catena della console passi il nome
scelto, e che il **corpo** che parte verso `/voice/tts` lo contenga davvero (montando un
motore con `pro` acceso e una fetch finta — si misura il contratto, non un'intenzione).

---

## C · La conversazione, per davvero

`app/conversa.py`

In quattro giri erano state aggiunte sei cose, tutte fatte bene. Il problema è che sono
**sei funzioni, e una conversazione non è una somma di funzioni**. Il criterio, al posto
dell'elenco: *una conversazione funziona quando chi parla non deve pensare a come parlare.*

### La scelta di fondo: una mossa cambia COSA si cerca

Non il tono — quello c'era già dal V6. **Cosa si va a cercare.** È questa la differenza
fra sei funzioni e una conversazione, ed è anche l'unica versione verificabile senza
chiamare il modello.

| La prova | Prima | Adesso |
|---|---|---|
| «Aspetta, non intendevo quello» | il filo anteponeva gli ultimi due turni utente: **rimetteva nella query proprio la frase appena ritirata** | il turno ritirato esce, resta quello prima |
| «E l'altro?» dopo due clienti | si cercava e si rispondeva su uno dei due | **non arriva al modello**: torna «quale dei due?» |
| «Lascia stare, dimmi invece…» | il vecchio soggetto restava nella query | il filo si taglia; senza domanda nuova, una riga e basta |
| «Ma sei sicura?» | si cercava *«ma sei sicura?»* nel vault → muro | si ricerca la **domanda di prima**, e il prompt impone di riaprire la fonte |
| silenzio, poi «allora?» | idem | si riprende la domanda in sospeso |

Due casi **non arrivano nemmeno al modello**. Con due soggetti in ballo e un «e l'altro?»
la risposta giusta è una domanda, e una domanda si compone dai due nomi che sono già nel
filo: costa zero, arriva subito (a voce conta) e soprattutto **non può indovinare** — che
è il comportamento che si voleva rendere impossibile, non solo improbabile. Stessa cosa
per «lascia stare» senza niente dopo: mandarla a un modello vorrebbe dire pagare un
round-trip per rischiare che risponda lo stesso alla domanda abbandonata.

Il «silenzio» della quinta prova è coperto dalla rete di sicurezza del V7: se il client ha
perso la history, i turni li ha il server (TTL 30').

### C2 · Le domande che non riguardano il cervello

*«Che ore sono a New York»* non è né il muro né la porta: è **rispondere**, per l'owner e
per il tenant con `libera`. Quello che cambia è una cosa piccola: **non si offre di
scriverci una nota**. Annotare nel vault l'ora di New York è una porta aperta sul niente,
e riempirebbe il cervello di spazzatura con la nostra firma sopra.

Il discrimine non può essere «c'è un nome proprio» — *New York* ne ha due. È **il mondo
del tenant**: gli scope che quel tenant può vedere, cioè esattamente ciò di cui il cervello
potrebbe sapere qualcosa. «Come si fa a fatturare ad ATS» ha la forma di una domanda
generale ed è una domanda sul cervello: lì l'offerta resta, perché il buco esiste.

### C3 · Il limite, di nuovo e intero

Il tono vale per tutti; il contenuto fuori dal vault no, salvo `libera` sul record del
tenant. C'è un test che lo prova su una domanda innocua, e uno che prova che **le mosse
non allargano i permessi**: ricordare che al turno prima si parlava di un cliente non dà
il diritto di leggere le sue note.

---

## Il metro dell'area «conversazione», da adesso

Il punteggio non si giustifica più con quante funzioni sono state aggiunte, ma con
**quante delle cinque prove passano**. Vivono in `tests/test_v10_conversazione.py`,
elencate nel dizionario `PROVE` in fondo al file, con un test che fallisce se una sparisce
dall'elenco senza sparire dai test.

Ieri sera non ne passava nessuna. Adesso cinque su cinque — e le cinque frasi le ho scelte
io, che è il limite scritto nel quadro: un riconoscitore provato contro i propri esempi
dimostra il meccanismo, non la copertura.
