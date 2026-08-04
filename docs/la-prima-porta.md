# V13 · La prima porta

> 3 agosto 2026. Giro corto di proposito: il codice non è il collo di bottiglia da martedì.

Il browser ha dimenticato le credenziali, e la console si è aperta così:

```
URL motore · Admin token · Chiave tenant
URL orchestratore · Admin token orchestratore · Tenant code
```

**Sei campi, due dei quali segreti, prima di vedere qualunque cosa.** Per chi conosce il
sistema è mezzo minuto. Ma il criterio del V11 dice: *una sezione esiste se un
imprenditore appena partito capisce in tre secondi perché aprirla* — e questa era **l'unica
porta che quel criterio non aveva mai incontrato**, oltre a essere la prima che si apre.

Non è un difetto introdotto dal V11: quella finestrella è nata quando il pannello lo usava
una persona sola. È diventata un problema quando il resto ha smesso di essere così.

---

## Il percorso, rovesciato

| prima | adesso |
|---|---|
| muro → sei campi → forse qualcosa | **guardo → capisco → collego** |

**Un campo.** La chiave del tenant, e basta — il guardiano lo conta a ogni push e diventa
rosso se tornano due.

**Cinque dietro un cassetto chiuso.** URL e token dei due servizi, tenant code: hanno tutti
un valore giusto che il pannello sa da sé (URL vuoto = stesso dominio, l'orchestratore vive
nello stesso progetto), e servono a un'installazione separata o a un collaudo. Il cassetto
si apre da solo se qualcosa di avanzato è già impostato: nasconderlo a chi lo ha
configurato sarebbe peggio che mostrarlo a chi non gli serve.

**E prima di tutto, un bottone per guardare.** La modalità demo esisteva già ma era una
spunta in fondo ai sei campi — cioè si poteva guardare Divina solo *dopo* aver deciso di
collegarla. Adesso è la prima cosa, ed è quella che fa capire cosa si sta collegando.

---

## La chiave che non passa più dagli appunti

Il modulo «Nuovo accesso cliente» chiedeva *«il VALORE della chiave tenant (`ovy_…` /
`ember_…`), non il nome»*, con la nota *«si vede UNA sola volta»*. Quindi, per creare un
cliente: emetti la chiave → copiala al volo → incollala in un altro modulo. **Tre passaggi,
e in mezzo un segreto che passa per gli appunti e per lo schermo.**

Adesso si indica **il cliente** — la sua cartella nel cervello — e la chiave **nasce sul
server**, legata a quello scope e a nient'altro. Non torna indietro nella risposta: non la
vede nemmeno chi crea l'accesso. C'è un test per ognuna di queste tre cose, e uno che tiene
in piedi la via vecchia per chi una chiave ce l'ha già.

**Meno passaggi e meno superficie sono la stessa cosa**, e qui si vede bene: sparisce anche
`state._lastKey`, che teneva una chiave in memoria per una scorciatoia che non esiste più.

---

## I numeri del giro

| | |
|---|---|
| campi della prima porta | **6 → 1** (cinque dietro «avanzate», chiuse) |
| righe del pannello | 4076 → 4106 (**+30**) |
| rotte senza chiamante dichiarato | **0** |

Le righe crescono, e va detto invece di essere aggirato: il cassetto «avanzate» e il
percorso «guarda prima» sono codice nuovo, e l'unica cosa che è uscita davvero è la
scorciatoia della chiave. Il numero che questo giro aveva dichiarato di voler muovere è
l'altro — **da sei campi a uno** — ed è quello che il guardiano conta.

---

## Cosa questo giro non ha fatto

Il percorso del cliente **non l'ha ancora percorso una persona**: il guardiano lo cammina a
ogni push, ma su fixture di demo. E la correzione del V12 sul filo va riprovata sul filo
vero dopo il redeploy. Sono le due righe che restano in cima all'elenco di ciò che nessuno
ha guardato, e nessuna delle due si chiude scrivendo altro codice.
