# V12 · Provare quello che non si vede

> 3 agosto 2026. Il V11 è riuscito — sei porte, Human fuori, la home che dice cosa fare —
> ma **nel provarlo in produzione sono saltati fuori due difetti che nessun test vedeva.**
> Li ha trovati qualcuno che ha aperto il pannello e ha provato a usarlo.

---

## A · I pulsanti della home non erano pulsanti

Nelle righe di «Cosa conviene fare oggi» le azioni erano così:

```html
<span class="pill">Riempila dal loro sito</span>
<span class="pill">Lancia una lettura</span>
```

`<span>`. Nessun gestore, nessun `role`, nessun `href`. **Sembravano bottoni e non facevano
niente**: Andrea li ha premuti e ha dovuto lanciare l'ingest dall'API.

**La regola del V11 era che una funzione spenta lo dichiari. Un pulsante finto è l'opposto
esatto** — e questo era finito proprio dentro la funzione nata per quella regola.

Adesso ogni riga ha un rimedio che **esegue**: la KB magra apre la proposta dal sito per
quel cliente, il vault non letto **lancia la lettura** (che dalla console non si poteva
lanciare da nessuna parte — è il motivo per cui quel bottone non poteva funzionare), le
proposte aprono la coda. E dove il rimedio non è collegabile — «manda un accesso a un
cliente» è una decisione, non un clic — **la riga resta e il bottone no**: meglio una
diagnosi senza rimedio che un rimedio finto.

### Il punto che conta più della correzione

Il controllo del V11 verificava che la home *dicesse* cosa fare, non che il rimedio
*funzionasse*. **Il guardiano adesso preme**, e registra cosa è successo a ognuno:

```
[premuti] Riempila dal loro sito → apre una finestra
          Lancia una lettura     → dice perché non può
          Guardale               → chiama l'API
```

Quattro esiti ammessi — chiama l'API, apre una finestra, cambia pagina, dice perché non
può — e un quinto che fa fallire la CI: **niente**. Il terzo caso conta: in demo la lettura
non può partire, e dirlo è il comportamento giusto; ma l'esito si registra uno per uno, così
un rimedio che si limita a parlare si vede nel log e se domani smettesse anche di parlare la
CI diventa rossa.

**Da qui in avanti: se il guardiano non la preme, l'azione non è provata.**

### Una scoria, e un difetto trovato cercandola

Il commento CSS orfano di Human (`/* Human · la figura a strati… */`) è uscito, insieme a
dodici regole CSS per nove classi che nessuno usava più.

---

## B · Il filo prendeva la nota sbagliata

Due turni, come li fa una persona:

> «Parlami del cliente HRH» → giusto, trova le note di HRH
> «E quanto paga al mese?» → *«Questo nel cervello non c'è.»*

Mentre nel vault c'è scritto **HRH, 200 €/mese**. Le fonti erano `kb-hrh` — la scheda
pubblica, quella che il bot mostra ai visitatori — invece di `cliente-hrh`, dove sta la
cifra.

### Misurato prima di correggere, e il sospetto era sbagliato

L'ipotesi era che l'espansione lessicale aggiungesse parole più simili alla KB che alla
scheda. Misurato:

```
False  'E quanto paga al mese?'      ← non riconosciuta come domanda di seguito
False  'Quanto paga al mese?'
False  'Da quando è cliente?'
True   'E il contratto?'
```

**L'espansione non partiva affatto.** `_ANAFORA` accettava «e» solo davanti a un articolo o
una preposizione («e il contratto?»), quindi **ogni domanda di seguito che comincia con una
parola interrogativa** cadeva fuori e finiva nel retrieval **senza soggetto**. Cercare
«quanto paga al mese» in tutto lo scope trova la nota che parla di pagamenti — non quella
che parla di HRH. Il difetto non era in cosa il filo aggiunge: era in cosa il filo
riconosce.

### La regola nuova, e il confine

Una domanda è di seguito anche quando è **corta e non porta nessun soggetto suo**, mentre
nel filo un soggetto c'è. «Soggetto» significa un nome proprio **o** un sintagma introdotto
da un articolo nudo:

| | |
|---|---|
| «E quanto paga **al** mese?» | `al` è una preposizione articolata: un complemento, non un soggetto → **di seguito** |
| «quanto costa **la** stampa 3D?» | `la` è un articolo nudo: la domanda ha il suo soggetto → **si regge da sola** |

E deve essere una domanda: senza il punto interrogativo si sarebbe finito a espandere
«ciao». I casi che il V7 aveva deciso restano tutti come li aveva decisi — c'è un test per
ognuno.

**La prova che resta** vive in `tests/test_v12_filo_scheda.py`: due turni, un indice finto
che sceglie per sovrapposizione di parole, e l'asserzione che la fonte sia `cliente-hrh` e
la risposta contenga 200. Se torna rossa, Divina ha ricominciato a dire che non lo sa
mentre la cifra c'è.

È anche la **sesta prova** della conversazione, e non l'ho trovata io.

---

## C · Rendere verificabile quello che non lo era

Ventotto task in «da verificare», e di undici non si poteva dire niente — non perché il
lavoro fosse dubbio, ma perché per vederle serve uno stato che non esiste: un cliente vero,
un guasto vero, una conversazione chiusa.

**Nessuna superficie nuova. Il guardiano attraversa quei percorsi:**

- **entra come cliente** con un account di collaudo e apre le sue tre pagine — verifica che
  le note siano le sue, che i buchi dichiarino di essere spenti, e che al cliente **non**
  arrivi la riga tecnica del degrado;
- **affida un lavoro a Dante** e verifica che «↗ affido a…» compaia nel filo (la demo adesso
  rispecchia anche la delega: con `agent` nella richiesta la risposta porta la fonte di tipo
  agent, come in produzione);
- **guarda i promemoria** e il «Dimentica» che li raggiunge, con la retention dichiarata;
- **spegne apposta una dipendenza** e guarda se la schermata lo dice.

### Il terzo difetto, trovato dalla prova nuova

L'ultimo controllo ha trovato subito qualcosa: in «Cosa so di te» l'avviso di funzione
spenta era attaccato **ai promemoria** e non alla lista delle memorie, che mostrava ancora
`emptyBox('Non so ancora niente di te')` — **cioè esattamente la frase che il V9 esisteva
per togliere**, nella pagina che l'aveva causata. Nessuno se n'era accorto perché nessuna
prova attraversava quella schermata con la dipendenza spenta.

---

## D · Il percorso del cliente, fino in fondo

Il V11 ha aggiunto la registrazione come azienda e nessuno l'ha percorsa: è finita in
produzione come i pulsanti finti. Adesso il guardiano cammina tutto il tragitto:

```
[percorso] registra → legge il sito (3 proposte con la fonte) → coda → il cliente la vede
```

Tre campi e nessun identificatore da inventare; alla conferma la lettura del sito parte
**nella stessa sequenza**, col sito già dentro. Ogni proposta porta la sua citazione, e la
finestra dice che non sta salvando niente.

---

## Il numero di questo giro

Non «quante righe in meno» (era il V11) e non un punteggio: **quante task in attesa hanno
adesso una prova che le percorre.** Delle undici che il prompt elencava come impossibili:
**nove**.

E la cosa che va detta accanto: **queste prove girano su dati di demo.** Provano il
cablaggio, non la produzione — e la distinzione è la stessa che tiene l'affidabilità a 9
invece che a 10. Il metodo che ha trovato i difetti di oggi resta quello: qualcuno che apre
il pannello e prova a usarlo.
