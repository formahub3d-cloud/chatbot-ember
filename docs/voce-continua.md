# La voce continua — stato, misure, e il confronto Voxtral

> 30-07-2026 · sostituisce P8. Obiettivo in una frase: parlare con Divina come
> si parla con una persona, potendola interrompere. Obiettivo misurabile:
> **< 800 ms dal silenzio dell'utente alla prima sillaba della risposta.**

## Cosa è stato fatto (4 tappe, un commit ciascuna)

| Tappa | Cosa cambia | Dove |
|---|---|---|
| PR1 | Sintesi **per frase** durante lo stream: la prima frase si sente mentre il resto arriva. Coda audio ordinata, chunker italiano (Dott., S.r.l., art. 3, 1.234,56, elenchi, ellissi). | `widget/embed.js` (`emSentenze`, `vout*`) |
| PR2 | **Interruzione a metà frase**: VAD sul microfono (echoCancellation), soglia adattiva + 220 ms di sostegno + 350 ms ciechi a inizio riproduzione; stop audio immediato + abort della generazione. | `widget/embed.js` (`vad*`) |
| PR3 | Trascrizione **con parziali live**: timeslice 1.2 s → `/voice/stt`, ultimo-vince, testo visibile mentre parli. | `widget/embed.js` (`proListenStart`) |
| PR4 | L'orb **respira col suono**: ampiezza reale in ingresso e in uscita → raggio/luminosità. | `panel/index.html` (console) |

Le chiavi restano sul server (proxy `/voice/*`), `prefers-reduced-motion`
continua a valere (voce sì, pulsazione no), la voce del browser resta come
rete di sicurezza, italiano lingua predefinita.

## Come si misura (in produzione — il sandbox non ha rete)

- **[voce] prima sillaba dopo N ms** in console del browser, a ogni risposta.
- `window.Divina.voiceStats` → `firstSyllableMs` (ultima), `samples` (storia),
  `interruptions`, `vad` (rms / base / soglia correnti, per tarare il barge-in
  coi numeri e non a occhio).
- Prima del fix il tempo era: *intera generazione* + *sintesi dell'intera
  risposta*; ora è: *prima frase generata* + *una sintesi breve*. Il valore
  assoluto va riportato dopo il collaudo su divina.formahub.it.

### Budget di latenza verso gli 800 ms (stime da verificare coi numeri)

| Voce | Stima | Nota |
|---|---|---|
| Fine parola → fine registrazione | ~0–300 ms | oggi il turno lo chiude l'utente col mic; con VAD di fine-frase si azzera |
| STT (scribe_v1, batch) | ~300–800 ms | il candidato n.1 da misurare; è QUI che Voxtral Realtime può cambiare la partita |
| Prima frase dal LLM (stream) | ~300–700 ms | dipende dal modello/carico |
| TTS prima frase (flash_v2_5) | ~75–200 ms | già a bassa latenza |
| Riproduzione (rete+decodifica) | ~50–150 ms | mp3 44.1k |

Se un numero manca l'obiettivo, si scrive DOVE sono i millisecondi: la
strumentazione sopra serve esattamente a questo.

## Il confronto per la trascrizione (PR3): restare o passare a Voxtral?

| | ElevenLabs `scribe_v1` (oggi) | **Mistral Voxtral Realtime** | Deepgram nova-3 (streaming WS) |
|---|---|---|---|
| Modalità | batch HTTP (ri-invio dell'accumulato ogni 1.2 s) | streaming reale, dichiara **< 200 ms** | streaming reale WS |
| Costo | ~0,007 $/min di audio **per invio** — coi parziali l'audio si ri-fattura: su 30 s di parlato ≈ 10–12× il costo del solo invio finale (cap a 90 s per contenerlo) | **~0,006 $/min**, l'audio passa UNA volta | ~0,0059 $/min |
| Contratti/chiavi | già attive | **stesso fornitore degli embeddings: zero contratti nuovi, zero chiavi nuove** | fornitore in più |
| Giurisdizione | USA | **UE** | USA |
| Lavoro server | zero (endpoint esistente) | proxy WebSocket da scrivere in `voice.py`/`main.py` | proxy WebSocket |

**Decisione: per ora si resta su scribe_v1 coi parziali.** Il motivo è di
metodo, non di merito: dal sandbox non si può misurare nulla, e cambiare
fornitore senza numeri è vietato dal task stesso. Voxtral Realtime è il
candidato naturale (costo pari o minore SENZA il moltiplicatore dei parziali,
latenza dichiarata < 200 ms, UE, stessa chiave Mistral) — il passaggio ha
senso appena: (1) il collaudo misura la voce «STT» del budget sopra i ~500 ms,
oppure (2) le sessioni vocali diventano lunghe/frequenti e il moltiplicatore
dei parziali pesa in bolletta. A quel punto: proxy WS server-side (le chiavi
NON scendono nel browser nemmeno lì) e A/B coi numeri di `voiceStats`.

## Checklist Railway (lato owner — da /admin/status si vede tutto)

- [ ] `VOICE_PROVIDER=elevenlabs` (confermato in produzione da /health)
- [ ] `ELEVENLABS_VOICE_ID` = **una voce italiana** dalla Voice Library.
      Se `voice_id_set: false` in `/admin/status`, l'italiano esce con
      timbro inglese e nessuna ottimizzazione di latenza vale la pena.
- [ ] `ELEVENLABS_MODEL` assente o `eleven_flash_v2_5` (il default è già lui)
