#!/usr/bin/env python3
"""V11 (2-08, sera) · Le task del giro «quello che toglie», come DATI.

Ottavo seed, stesso stampo: brain_tasks, kind='audit', idempotency_key stabile
(`audit-2026-08-02-57` … `-64`). Rilanciarlo non duplica.

**Va lanciato PRIMA del merge**: `audit-merge` legge le chiavi citate nei commit.

Uso:
    EMBER_URL=https://divina.formahub.it ADMIN_TOKEN=... \
        python3 scripts/seed_task_v11_2026_08_02.py
"""
import os
import sys

_K = "audit-2026-08-02-"

TASK_V11 = [
    (_K + "57", "Sei destinazioni invece di diciotto", "alta",
     "Andrea: «Non so cosa devo fare per migliorare Divina o migliorare la mia azienda. È "
     "tutto un po' controintuitivo. Ci sono tanti pulsanti su cui non sono mai andato "
     "sopra.» Il dato che gli dà ragione: la barra ha diciotto destinazioni e in una "
     "giornata intera dentro quel pannello, conoscendo il codice, ne sono state aperte "
     "cinque. Le altre tredici non le ha aperte nessuno, mai, in due giorni. La causa è "
     "nostra: V6 l'orbita, V7 il filo, V8 «Cosa so di te» e il pannello cliente, V9 la KB "
     "dal sito — ogni cosa fatta bene, ognuna con la sua sezione, e nessun giro ha mai "
     "tolto niente. Il criterio, unico: una sezione esiste se un imprenditore appena "
     "partito, che non sa niente di AI, capisce in tre secondi perché aprirla."),
    (_K + "58", "«Human · evoluzione» esce dal pannello", "alta",
     "È la scheda personale di Andrea, è vuota (tutte le voci sono «da definire») e non "
     "c'entra niente con un prodotto che si vende alle PMI. Toglierla è anche un guadagno "
     "di sicurezza, non solo di ordine: è l'unico posto del sistema pensato per contenere "
     "dati sanitari, che nel GDPR sono una categoria speciale. Finché il motore gira in US "
     "West la scelta più difendibile non è proteggerla meglio: è non averla. La nota resta "
     "nel vault, fuori dall'indice, come adesso."),
    (_K + "59", "Il codice delle viste tolte va cancellato", "alta",
     "Andrea: «più cose aggiungiamo, più c'è vulnerabilità». Ogni endpoint che nessuna "
     "schermata chiama è superficie d'attacco che nessuno guarda — e che nessuno noterà "
     "quando smetterà di funzionare. Il contract test dice già quali rotte esistono e chi "
     "le usa: serve la direzione opposta, cioè quali rotte non chiama nessuno. Se una "
     "serve a uno script di manutenzione e non alla console si tiene, ma si DICHIARA."),
    (_K + "60", "La home dice tre cose da fare oggi, con la ragione", "alta",
     "Alla domanda «cosa faccio oggi» il pannello rispondeva con cinquanta task da fare e "
     "venti da verificare. Settanta righe non sono una guida: sono una lista che paralizza, "
     "e si allunga a ogni giro. Tre cose, mai di più, ognuna con la ragione in una riga "
     "scritta in italiano, che parla della sua azienda e non del software. Si scelgono da "
     "segnali veri che il sistema ha già — KB sotto soglia, ingest vecchio, proposte in "
     "coda, buchi ripetuti. Se un criterio non c'è, quella riga non si mostra: meglio due "
     "righe vere che tre di cui una inventata."),
    (_K + "61", "Il cliente si registra come azienda", "alta",
     "Oggi un cliente esiste quando Andrea gli emette una chiave a mano. Deve diventare un "
     "percorso: si registra come azienda (nome, sito, settore), Divina legge il suo sito e "
     "propone la prima knowledge base, lui la guarda e la corregge — ed è il primo momento "
     "in cui capisce cosa sta comprando — e da lì la KB cresce con le conversazioni, sempre "
     "come proposte. Il pezzo che manca è solo il primo: gli altri tre sono già costruiti e "
     "vanno messi in fila."),
    (_K + "62", "Divina si documenta dentro il proprio cervello", "alta",
     "Idea di Andrea, la più originale del giro: «Divina deve sapere come funziona e come "
     "si può migliorare. Non devi saperlo solo tu, ma anche lei.» Oggi sa tutto dei clienti "
     "di FORMA e niente di sé stessa: se un cliente le chiede «cosa puoi fare per la mia "
     "azienda?» risponde da istruzioni scritte nel codice, cioè da qualcosa che nessuno può "
     "leggere, correggere o citare. La soluzione è la stessa architettura di tutto il "
     "resto: note nel vault, in ovyon/, citate come fonti. Il vantaggio non è filosofico — "
     "quelle note si aggiornano senza toccare il codice, e chiunque può vedere se ciò che "
     "dice di sé è vero."),
    (_K + "63", "Divina sa dire a che punto è il lavoro con un cliente", "media",
     "«Cosa sto consegnando e perché» significa saper dire: «la tua KB ha dodici voci, ne "
     "mancano gli orari e i prezzi, e finché non ci sono il bot dirà che non sa "
     "rispondere.» Il dato c'è già — sono i buchi e le proposte in coda — manca che sappia "
     "raccontarlo."),
    (_K + "64", "A fine conversazione: cosa è emerso e cosa conviene fare", "media",
     "learned.py propone già da zero a tre «cose imparate» con la citazione. Qui serve un "
     "passo diverso e più utile per il cliente: cosa è emerso e cosa conviene fare, non "
     "solo cosa ricordare. Due o tre righe, e come sempre proposta, mai scrittura "
     "automatica."),
]


def seed(post) -> list[dict]:
    """Idempotente (chiave stabile). `post(path, json) -> dict` è il trasporto."""
    esiti = []
    for key, titolo, priorita, nota in TASK_V11:
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
    print("Seed V11 completato (idempotente: rilanciarlo non duplica).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
