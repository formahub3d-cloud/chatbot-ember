#!/usr/bin/env python3
"""V12 (3-08) · Le task del giro «provare quello che non si vede», come DATI.

Nono seed, stesso stampo: brain_tasks, kind='audit', idempotency_key stabile
(`audit-2026-08-03-65` … `-71`). Rilanciarlo non duplica.

**Va lanciato PRIMA del merge**: `audit-merge` legge le chiavi citate nei commit.

Uso:
    EMBER_URL=https://divina.formahub.it ADMIN_TOKEN=... \
        python3 scripts/seed_task_v12_2026_08_03.py
"""
import os
import sys

_K = "audit-2026-08-03-"

TASK_V12 = [
    (_K + "65", "Le azioni della home si possono premere davvero", "alta",
     "Nelle righe di «Cosa conviene fare oggi» le azioni erano <span class=\"pill\">: nessun "
     "gestore, nessun role, nessun href. Sembravano bottoni e non facevano niente — Andrea "
     "li ha premuti e ha dovuto lanciare l'ingest dall'API. La regola del V11 era che una "
     "funzione spenta lo dichiari: un pulsante finto è l'opposto esatto, ed è finito "
     "proprio dentro la funzione nata per quella regola. Se un'azione non è collegabile, "
     "la riga non mostra il bottone: meglio una diagnosi senza rimedio che un rimedio finto."),
    (_K + "66", "Il guardiano preme i rimedi, non li legge", "alta",
     "Il controllo del V11 verificava che la home DICESSE cosa fare, non che il rimedio "
     "funzionasse. Seicentonovantuno test, e nessuno che cliccasse quel bottone. Da qui in "
     "avanti vale per ogni azione nuova: se il guardiano non la preme, non è provata. E "
     "l'esito di ogni pressione si registra — chiama l'API, apre una finestra, cambia "
     "pagina o dice perché non può; «niente» fa fallire la CI."),
    (_K + "67", "La domanda di seguito trova la scheda, non solo la KB", "alta",
     "Provato due volte in produzione: «Parlami del cliente HRH» → «E quanto paga al mese?» "
     "rispondeva «questo nel cervello non c'è» mentre nel vault c'è HRH 200 €/mese. Le "
     "fonti erano kb-hrh (la scheda pubblica) invece di cliente-hrh. Il sospetto era che "
     "l'espansione aggiungesse parole simili alla KB; misurato, l'espansione NON partiva: "
     "_ANAFORA accettava «e» solo davanti a un articolo o una preposizione, quindi ogni "
     "domanda di seguito che comincia con una parola interrogativa finiva nel retrieval "
     "senza soggetto. Adesso una domanda corta che non porta nessun soggetto proprio, "
     "quando nel filo un soggetto c'è, è di seguito."),
    (_K + "68", "Il guardiano entra come cliente e apre le tre pagine", "alta",
     "Tre task erano non verificabili perché servono le credenziali di un cliente, che non "
     "esistono. Il guardiano entra con un account di collaudo e apre la sua KB, i suoi "
     "buchi e la chat: verifica che le note siano le sue, che i buchi dichiarino di essere "
     "spenti e che al cliente NON arrivi la riga tecnica del degrado."),
    (_K + "69", "Una dipendenza spenta apposta, per provare il degrado", "media",
     "Il degrado dichiarato non si poteva verificare perché in produzione non manca più "
     "niente: si vedrebbe solo rompendo qualcosa. Il guardiano lo rompe apposta e guarda "
     "se la schermata lo dice. Ha trovato subito un difetto vero: in «Cosa so di te» "
     "l'avviso era attaccato ai promemoria e NON alla lista delle memorie, che mostrava "
     "ancora «Non so ancora niente di te» — cioè esattamente la frase che il V9 esisteva "
     "per togliere."),
    (_K + "70", "La delega e la scheda-risultato provate da una prova", "media",
     "Servivano un lavoro affidato a un agente e una conversazione chiusa: due stati che "
     "in demo non esistevano. Adesso la demo rispecchia anche la delega (con `agent` nella "
     "richiesta la risposta porta la fonte di tipo agent, come in produzione), e il "
     "guardiano affida un compito a Dante e verifica che «affido a…» compaia nel filo."),
    (_K + "71", "Il percorso del cliente provato dall'inizio alla fine", "alta",
     "Il V11 ha aggiunto la registrazione come azienda e nessuno l'ha percorsa: è finita in "
     "produzione come i pulsanti finti. Il guardiano cammina tutto il tragitto — si "
     "registra (nome, sito, settore), Divina legge il sito e propone con la fonte, la "
     "proposta finisce in coda, il cliente la vede nel suo pannello — e dove la catena si "
     "interrompe lo scrive, invece di compensarlo con un'istruzione."),
]


def seed(post) -> list[dict]:
    """Idempotente (chiave stabile). `post(path, json) -> dict` è il trasporto."""
    esiti = []
    for key, titolo, priorita, nota in TASK_V12:
        r = post("/admin/tasks", {"kind": "audit", "title": titolo, "note": nota,
                                  "status": "aperta", "priorita": priorita,
                                  "idempotency_key": key})
        t = (r or {}).get("task") or {}
        esiti.append({"key": key, "id": t.get("id"), "status": t.get("status", "?"),
                      "priorita": t.get("priorita", priorita)})
    return esiti


def main() -> int:
    import json as _json
    import urllib.request
    base = os.environ.get("EMBER_URL", "http://localhost:8000").rstrip("/")
    tok = os.environ.get("ADMIN_TOKEN", "")
    if not tok:
        print("ADMIN_TOKEN mancante", file=sys.stderr)
        return 2

    def post(path, body):
        # urllib, non httpx (regola dell'1/08): gira col Python di sistema.
        req = urllib.request.Request(base + path, data=_json.dumps(body).encode(),
                                     headers={"Authorization": f"Bearer {tok}",
                                              "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return _json.loads(r.read().decode())

    for e in seed(post):
        print(f"  {e['key']} · {e['status']} · {e['priorita']} · id={e['id']}")
    print("Seed V12 completato (idempotente: rilanciarlo non duplica).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
