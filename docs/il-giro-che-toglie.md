# V11 · Il giro che toglie

> 2 agosto 2026, sera. Il primo giro che riduce. Nasce da una frase di Andrea, che è la
> valutazione più utile ricevuta finora:
>
> *«Non so cosa devo fare per migliorare Divina o migliorare la mia azienda. È tutto un
> po' controintuitivo. Ci sono tanti pulsanti su cui non sono mai andato sopra.»*

Il dato che gli dà ragione: la barra laterale aveva **diciotto destinazioni**, e in una
giornata intera dentro quel pannello — conoscendo il codice — ne sono state aperte
**cinque**. Le altre tredici non le ha aperte nessuno, mai, in due giorni.

**La causa è nostra:** V6 l'orbita, V7 il filo, V8 «Cosa so di te» e il pannello cliente,
V9 la KB dal sito, V10 le prove della conversazione. Ogni cosa fatta bene, ognuna con la
sua sezione. **Nessun giro aveva mai tolto niente.**

Il criterio, unico, per tutto il giro:

> **Una sezione esiste se un imprenditore appena partito, che non sa niente di AI, capisce
> in tre secondi perché aprirla.**

---

## A · Cosa resta e cosa esce

**Sei destinazioni** — Divina · Il cervello · I clienti · La squadra · Integrazioni ·
Impostazioni. Le altre tredici stanno sotto **«Amministrazione»**, che compare solo a chi
ha il token del motore e nasce chiusa. Non sono cancellate: servono a chi *gestisce* il
servizio, non a chi lo usa, e il problema non era che esistessero — era che occupassero
tredici righe nella barra di un imprenditore che vuole solo far rispondere il suo bot.

**«Human · evoluzione» esce del tutto.** Vuota, fuori tema, e — la ragione che pesa di più
— l'unico posto del sistema pensato per contenere **dati sanitari**, categoria speciale nel
GDPR, mentre il motore gira in US West. La scelta difendibile non è proteggerla meglio: è
non averla. La nota resta nel vault, fuori dall'indice, come prima.

### Il contratto al contrario

Andrea: *«più cose aggiungiamo, più c'è vulnerabilità.»* Il contratto console↔motore
andava in una direzione sola — il pannello che chiama una rotta inesistente fa CI rossa.
Adesso va anche nell'altra: **una rotta che non chiama nessuno.**

Ne sono uscite **quindici**, e nessuna era un difetto: hanno un chiamante fuori dal repo —
il connettore MCP, Stripe che chiama noi, gli obblighi di legge (art. 15/17) che si
eseguono a mano. Ma il chiamante adesso è **dichiarato con un nome**, e una rotta nuova
senza dichiarazione fa fallire la CI. È la differenza fra tenere una cosa e dimenticarsela
— e anche fra una dichiarazione e un «serve»: il test rifiuta le motivazioni vaghe.

### Il numero, e una tensione da dire

| | righe |
|---|---|
| tolte dal pannello (Human, la funzione morta, il controllo del guardiano) | **−102** |
| aggiunte da B, C e D | **+138** |
| **netto sul pannello** | **+36** |

**Il blocco A ha tolto; il giro nel suo insieme no**, e vale la pena dire perché invece di
aggiustare il conto. A2 dice esplicitamente *«non si cancellano»* delle tredici
destinazioni: il codice di dodici di loro resta per scelta. L'unica vista davvero
eliminabile era Human. Quindi «quante righe in meno» misura bene il blocco A e male il
giro, e la riduzione vera sta in un altro numero: **da diciotto destinazioni a sei.**

Fuori dal pannello il conto è netto: −28 righe in `app/main.py` (l'endpoint `/admin/human`)
e un file di test intero.

---

## B · La schermata che dice cosa fare oggi

Alla domanda «cosa faccio oggi» il pannello rispondeva con cinquanta task da fare e venti
da verificare. **Settanta righe non sono una guida: sono una lista che paralizza**, e si
allunga a ogni giro.

Al loro posto, e al posto dei quattro riquadri della home (un orologio, gli ultimi
dispatch, le task chiuse, le contraddizioni — quattro cose vere, nessuna che dicesse cosa
fare), **tre cose, mai di più**, ognuna con la ragione in una riga che parla dell'azienda:

```
▸ La knowledge base di HRH ha due note.
  Se ti chiamano e il bot non sa rispondere, la brutta figura è tua.
▸ Il cervello non legge il vault da 3 giorni.
  Quello che hai scritto martedì, Divina non lo sa ancora.
▸ Nessun cliente ha mai aperto il suo pannello.
  È la cosa che stai vendendo, e non l'ha ancora vista nessuno.
```

I quattro criteri vengono da dati che il sistema ha già: le note per tenant, il confronto
fra il commit del vault e quello dell'ultima ingest, la coda delle proposte, l'ultimo
accesso dei clienti. **Se il criterio non c'è, la riga non si mostra** — meglio due righe
vere che tre di cui una inventata. In demo ne compare **una sola**, ed è il comportamento
giusto: una guida che riempie il terzo posto per simmetria smette di essere una guida il
primo giorno in cui va tutto bene.

Sotto, un solo collegamento: **«mostrami tutto»**. La lista completa esiste ancora, per chi
la vuole.

---

## C · Il cliente si registra come azienda

Quattro passi, e solo il primo mancava:

1. **si registra come azienda** — nome, sito, settore. Nient'altro;
2. **Divina legge il suo sito** e propone la prima KB (V9/B, esiste);
3. **lui la guarda e la corregge** (V8/B, esiste) — il primo momento in cui capisce cosa
   sta comprando;
4. **da lì la KB cresce** con le conversazioni (V6/B3, esiste).

Il modulo di prima chiedeva «cartella (scope)», «referente» e «stato»: tre campi che a un
imprenditore non dicono niente e che si ricavano o si rimandano. Lo scope si deriva dal
nome. Il **sito** invece è la cosa che fa partire tutto il resto, e prima non si chiedeva
affatto. Alla conferma, il passo 2 parte nella stessa sequenza: è questo che trasforma tre
funzioni in un percorso.

I tre agenti restano tre. Nessun sub-agente nuovo, nessuna skill in più.

---

## D · Divina deve sapere come funziona

*«Divina deve sapere come funziona e come si può migliorare. Non devi saperlo solo tu, ma
anche lei.»* — è l'idea più originale del giro, ed è di Andrea.

Oggi Divina sa tutto dei clienti di FORMA e **niente di sé stessa**: a «cosa puoi fare per
la mia azienda?» rispondeva da istruzioni scritte nel codice, cioè da qualcosa che nessuno
può leggere, correggere o citare.

**D1** · Due note nel vault — `ovyon/divina/01-cosa-so-fare` e `02-come-mi-alimenti` — che
dicono cosa sa fare, cosa **non** fa e perché, e le quattro cose che la migliorano davvero,
in ordine di quanto pesano. Quando glielo chiedono, risponde **citandole**: fonte apribile
e correggibile, come qualunque altra risposta. Il vantaggio non è filosofico — quelle note
si aggiornano senza toccare il codice.

*Perché dal disco e non dall'indice.* `ovyon/` è uno scope, e uno scope è un permesso: un
tenant cliente non lo ha e non deve averlo. Allargare il filtro per una funzione di
documentazione vorrebbe dire spostare una decisione di sicurezza dentro un problema di
prodotto. Queste note sono **pubbliche per natura** — è quello che si racconta in una demo
— quindi hanno un canale loro, in sola lettura, su **una cartella costante**: mai un
percorso costruito da chi fa la domanda.

**D2** · «Cosa sto consegnando e perché»: sulla scheda di ogni cliente, una frase — *«la
knowledge base di ATS ha dodici voci. Mancano gli orari e i prezzi: finché non ci sono, a
chi lo chiede il bot risponde che non lo sa.»* Il dato c'era già; mancava che qualcuno lo
raccontasse, e la conseguenza conta più del buco.

**D3** · A fine conversazione, accanto a «cosa abbiamo imparato», una domanda diversa:
**cosa è emerso e cosa conviene fare**. Non si ricava dalla prima — una preferenza da
ricordare non è un'azione da proporre. Stesse due cautele di sempre: ogni riga porta la
citazione verificata alla lettera, e niente viene scritto.

---

## La regola che resta

**Ogni giro d'ora in avanti toglie qualcosa.** Una sezione che nessuno apre da due
settimane non è una funzione in attesa: è un costo che si paga ogni volta che si cerca
qualcos'altro, e una superficie in più da difendere. Se un giro non ha niente da togliere,
si toglie il giro.
