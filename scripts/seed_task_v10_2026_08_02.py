#!/usr/bin/env python3
"""V10 (2-08, sera) · Le task del giro «la conversazione, e due cose che si
spengono da sole», come DATI.

Settimo seed, stesso stampo dei sei precedenti: brain_tasks, kind='audit',
idempotency_key stabile (`audit-2026-08-02-51` … `-56`). Rilanciarlo non duplica.

**Va lanciato PRIMA del merge**: `audit-merge` legge le chiavi citate nei commit
e non può spostare task che non esistono ancora.

Uso:
    EMBER_URL=https://divina.formahub.it ADMIN_TOKEN=... \
        python3 scripts/seed_task_v10_2026_08_02.py
"""
import os
import sys

_K = "audit-2026-08-02-"

# (chiave, titolo, priorità, nota di nascita)
TASK_V10 = [
    (_K + "51", "Il clone del vault è una dipendenza dichiarata", "alta",
     "Visto due volte il 2/08, la seconda con conseguenze. Dopo ogni redeploy su Railway "
     "il container è nuovo e il clone del vault non c'è: vault_info() torna {}, e siccome "
     "l'allarme sui commit ha bisogno di DUE valori per confrontarli si spegne da solo "
     "senza dichiararlo. Alle 17:40 il V9 era mergiato da venti minuti e il pannello "
     "mostrava ancora il quadro del V8, con la fascia vuota — cioè con l'aria che andasse "
     "tutto bene. Non è un caso raro: succede a ogni configurazione, e quel giorno le "
     "variabili di Railway sono state toccate cinque volte. dbcheck non può vederlo (non "
     "è una tabella), quindi serve un accertamento suo dentro app/degrado.py."),
    (_K + "52", "L'ingest si procura il vault al primo avvio", "alta",
     "Un allarme che si spegne a ogni deploy e che qualcuno deve riaccendere a mano è un "
     "allarme che prima o poi non riaccende nessuno. Se il motore all'avvio si accorge di "
     "non avere il clone, se lo procura, coi freni che esistono già. Scelta motivata sul "
     "confine: si prende il CLONE, non si reindicizza. Qdrant sta fuori dal container e "
     "sopravvive al redeploy — l'indice non è sparito, è sparito il metro. Una ingest "
     "completa all'avvio ricalcolerebbe gli embedding di ogni nota per riscrivere lo "
     "stesso indice, e su Railway (che riavvia anche senza deploy) trasformerebbe un "
     "ciclo di riavvii in un ciclo di reindicizzazioni contro l'API degli embedding."),
    (_K + "53", "Alla richiesta TTS arriva il nome dell'agente giusto", "alta",
     "Andrea: «gli agenti parlano ancora tutti con la stessa voce». Misurato prima di "
     "correggere, perché il sospetto era un altro: la tubatura è giusta da cima a fondo, "
     "speak() riceve agente='dante' e il server ha quattro voci diverse (58.559 · 63.156 "
     "· 48.946 byte sullo stesso testo). Il difetto è che NESSUNA voce parte: la lettura "
     "ad alta voce nasce spenta e l'unico comando è un'icona con un tooltip, invisibile su "
     "un telefono. Una funzione che c'è ma non parte si scambia per una funzione rotta, e "
     "sono due riparazioni diversissime. Serve anche un controllo nel guardiano: è "
     "esattamente il tipo di difetto che sopravvive a 660 test verdi."),
    (_K + "54", "Le cinque prove della conversazione vera", "alta",
     "In quattro giri sono state aggiunte sei cose — tono per tutti, muro che diventa "
     "porta, filo, memoria, riassunti, capacità parlando — tutte fatte bene, e l'area è "
     "passata da 4 a 8. Ma sei funzioni non fanno una conversazione: Divina risponde bene "
     "se le fai la domanda giusta nel modo giusto. Le cinque prove che contano: «aspetta, "
     "non intendevo quello» (torna indietro di un turno), «e l'altro?» dopo due clienti "
     "(chiede quale invece di indovinare), «lascia stare, dimmi invece…» (abbandona senza "
     "rispondere lo stesso), «ma sei sicura?» (riapre la fonte invece di riformulare), "
     "silenzio poi «allora?» (riprende dal punto in sospeso)."),
    (_K + "55", "Rispondere alle domande che non riguardano il cervello", "media",
     "«Che ore sono a New York», «come si scrive un'email di sollecito»: la domanda non "
     "riguarda il cervello, e la risposta giusta non è né il muro né la porta — è "
     "rispondere, per l'owner e per il tenant con `libera`. È il caso più comune di "
     "conversazione normale e non c'era un test che lo coprisse. Il limite resta intero: "
     "senza quel permesso il muro non si tocca, perché il widget sul sito di un cliente "
     "non può inventare sul cliente."),
    (_K + "56", "Il punteggio della conversazione si misura, non si stima", "media",
     "Il punteggio dell'area 5 saliva di un punto ogni volta che si aggiungeva una "
     "funzione. Da adesso si giustifica con quante delle cinque prove passano: un metro "
     "contabile al posto di una stima. Le prove vivono nei test, elencate in un posto "
     "solo — se una sparisce di lì senza sparire dal quadro, il quadro mente."),
]


def seed(post) -> list[dict]:
    """Idempotente (chiave stabile). `post(path, json) -> dict` è il trasporto:
    urllib in produzione, TestClient nei test — stessa logica, testabile."""
    esiti = []
    for key, titolo, priorita, nota in TASK_V10:
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
    print("Seed V10 completato (idempotente: rilanciarlo non duplica).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
