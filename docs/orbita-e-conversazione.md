# V6 · L'orbita che si guarda, e Divina che parla

> 1 agosto 2026, notte. Due progetti, non sette rifiniture. Il primo è estetico;
> il secondo è il punto fermo a 4/10 da tre giorni — quello che separa un motore
> di ricerca che parla da un assistente.

---

## Parte A · L'orbita

### Il criterio

> **Lo stato si legge dalla forma e dal colore. Le parole, se servono, sono UNA
> riga — mai venti etichette.**

Prima la home era una fascia con dentro un grafo etichettato: passavi col mouse
e comparivano i nomi delle note. Chi guarda la home non sta cercando una nota:
sta guardando se il cervello è vivo. Quindi l'orbita prende la scena, i nomi
spariscono (`labels:'none'`: mai testo, mai hover, nemmeno al passaggio), e
«La squadra», «Fatte di recente» e «Contraddizioni» restano — sotto.

### I quattro stati

| Stato | Cosa fa l'orbita | Da dove viene il dato |
|---|---|---|
| **a riposo** | respira (ciclo ~4 s, ampiezza 1,4%), rotazione lentissima, grigio | default |
| **pensa** | i nodi si contraggono verso il centro e si riaprono | `state._pensa`, acceso da `chatTurn` |
| **lavora** | un'onda attraversa la superficie dal punto dell'agente verso l'esterno | `/agents/dispatches` (ultimi 10') |
| **legge il vault** | i nodi si accendono a cascata, come una scansione | `last_ingest` di `/admin/brain`, fresco di minuti |

Il **respiro** esiste per un motivo che non è decorativo: un sistema fermo e un
sistema rotto si somigliavano troppo. Il punto dell'onda («lavora») è derivato
da un hash stabile del nome dell'agente: lo stesso agente parte sempre dallo
stesso punto, così il movimento diventa riconoscibile invece di casuale.

### I colori

| Agente | Colore | Nota |
|---|---|---|
| Divina | `#EAB308` giallo | era viola |
| Dante | `#E4342B` rosso | era `#F8693C`, cioè lo **stesso token** dell'arancione degli avvisi |
| Virgilio | `#0ED4E4` azzurro | invariato |
| Beatrice | `#DD24F2` | invariato |
| nessuno | `#7f8aa0` grigio | lo stato normale, e deve essere bello anche così |

La transizione fra due colori dura **600 ms** — mai uno scatto — e se due agenti
lavorano insieme il colore è un **gradiente fra i due** lungo la sfera: mostra la
collaborazione invece di nasconderla.

Su tema chiaro giallo e rosso pieni non passano il contrasto AA: esistono shade
dedicati (`--divina:#946300`, `--dante:#B3261E`). Il colore identifica, il testo
deve leggersi.

### L'unica riga di testo, e perché non è una rifinitura

Sotto l'orbita c'è una frase in italiano che cambia con lo stato:
*«Virgilio sta lavorando · sta cercando nel cervello»*, *«Il cervello sta leggendo
il vault»*, *«A riposo · 106 neuroni · vault letto 2 ore fa»*.

Sostituisce venti tooltip con una frase. Ma il motivo per cui deve esserci non è
estetico: **il colore da solo non può portare l'informazione.** Chi non distingue
il rosso dall'azzurro deve poter capire lo stesso cosa sta succedendo. È
accessibilità, e per questo il guardiano la controlla (V6-2): forza i tre stati e
fallisce se la riga non li nomina.

Vale la regola di sempre: **senza dato la riga dice «—»** e l'orbita resta grigia.
Un'orbita che finge di lavorare è peggio di una ferma.

### La settima area

Il quadro di potenziamento aveva sei aree; l'estetica era l'unica cosa che si
giudicava a sensazione. Adesso è la settima — «Estetica e resa visiva» — con un
punteggio, uno storico e delle task. Il radar è diventato un ettagono senza
toccare il codice del radar (era già generico su N).

La media **scende** da 6,2 a 6,0. Non perché sia peggiorato qualcosa: perché
un'area che si stava ignorando era sotto la media. È il motivo per cui si misura.

---

## Parte B · La conversazione

### B1 · Il muro diventa una porta

Prima: *«Non ho questa informazione nelle aree a cui ho accesso.»* Corretto e
inutile — chiudeva la conversazione invece di aprirla.

Adesso: *«Questo nel cervello non c'è: nelle aree a cui ho accesso non lo trovo.
Se vuoi, aggiungiamolo adesso — così la prossima volta lo so.»*

E l'offerta è **attaccata alla risposta**, non in un menu altrove: la risposta
porta un campo `gap` e la console ci disegna sotto il bottone che apre il
write-back. Il buco che qualcuno scopre è il momento in cui è più facile
riempirlo.

Due dettagli che sembrano piccoli e non lo sono:

- la domanda torna indietro come **titolo pronto da salvare**, quindi è redatta
  dalle PII come nei log: un IBAN scritto in chat non rientra nel vault passando
  di lì;
- il **corpo della nota resta vuoto** e lo scrive una persona. Salvare la
  risposta «non lo so» sarebbe un buco archiviato, non colmato.

### B2 · La distinzione che non si può perdere

| | Owner (FORMA) | Tenant cliente |
|---|---|---|
| Saluti, chiacchiera, cambio argomento, tornare indietro | ✅ | ✅ |
| Ammettere il buco con una frase umana e offrire di colmarlo | ✅ | ✅ |
| Rispondere con conoscenza generale fuori dal vault | ✅ | ❌ salvo spunta `libera` |

Il tono è uno **strato del system prompt** (`rag._TONO_IT`), aggiunto sempre e per
chiunque; dice esplicitamente che riguarda solo la forma e che ogni affermazione
specifica continua a venire dal CONTENUTO. La conoscenza generale è invece un
**flag del record** (`tenant_flags.libera`, stessa famiglia di `owner` e `liv3`),
letto server-side, mai una scelta nella richiesta.

Il motivo: il giorno che ATS installa Divina, quel bot parla a nome di ATS — e la
promessa che gli si vende è che ciò che dice viene dal loro materiale.

Un test tiene ferma la distinzione: se un domani qualcuno mettesse la deroga
dentro lo strato di tono, diventa rosso.

### B3 · Le conversazioni diventano cervello

A fine conversazione (o su richiesta, dal bottone «Cosa abbiamo imparato»),
Divina propone **da zero a tre** cose imparate, ciascuna con la **citazione** del
punto della conversazione da cui viene. Vanno nella coda Proposte che esisteva
già. Approvate → nota nel vault, marcata come nata da conversazione, con la
citazione dentro. Rifiutate → spariscono.

Le tre regole, applicate in codice e non per convenzione:

1. **Mai salvare in automatico.** `learned.proponi()` non scrive: ritorna
   candidati. La scrittura resta il write-back a due tempi. Se la scrittura
   fallisce, la proposta torna in coda — mai un «fatto» senza il fatto.
2. **Ogni proposta porta la sua fonte.** La citazione viene **verificata**
   contro il testo della conversazione (confronto normalizzato ma letterale):
   una citazione che il modello ha ricostruito a memoria fa cadere la proposta.
   Una nota senza provenienza è una voce di corridoio.
3. **Zero dati personali.** Un candidato con PII si **scarta**, non si redige:
   una nota con «[email]» dentro è peggio di una nota che non esiste. E
   `andrea-aloia/human/` non c'entra mai — nessuna proposta può indirizzarsi lì.

---

## Perché non un terzo modello

Andrea ha chiesto se convenisse aggiungere GPT e Kimi e farli discutere fra loro.
**No, non adesso**: il 4/10 della conversazione non era un problema di
intelligenza del modello, era che quello strato non esisteva. Un modello più
bravo avrebbe dato la stessa risposta di prima, a un costo maggiore. In più:
costo ×3, latenza in secondi (col modo vocale a 55 ms di prima sillaba sarebbe un
passo indietro), i modelli concordano quasi sempre quando leggono lo stesso
vault, e ogni fornitore nuovo è un sub-processor nuovo mentre il DPA è già da
riscrivere per US West.

Si riprende quando la conversazione funziona, non prima. È scritto qui e non in
una task perché una decisione presa e motivata non deve tornare ogni due
settimane come se fosse nuova.

## Deciso, ma non in questo giro

**L'automatismo dell'audit sul merge** (task `audit-2026-08-01-32`). La semantica
è già decisa: **il merge NON chiude le task, le mette «da verificare»**. Diventano
«fatta» solo dopo che Andrea le ha guardate — la stessa logica di
`CONFERMA_VISTA`, che l'1/08 ha già dimostrato di servire. Il punteggio del quadro
e lo storico, invece, possono aggiornarsi da soli: sono una media di numeri
scritti a mano, non un giudizio.
