#!/usr/bin/env python3
"""V6 (1-08 notte) · Le task che il prompt V6 produce, come DATI.

Quarto seed, NON una modifica dei tre del 31-07: quelli sono già girati in
produzione e restano riproducibili com'erano. Stesso stampo: brain_tasks,
kind='audit', idempotency_key stabile (audit-2026-08-01-22 … -32, continuando
dal 21 già usato) — rilanciare non duplica niente.

Differenza dai seed precedenti: qui la PRIORITÀ viaggia con la task, invece di
arrivare dopo con uno script separato. Il giudizio nasce insieme alla task
perché era già scritto nel prompt: separarlo sarebbe stato solo un giro in più.

Nota di sovrapposizione, dichiarata e non aggiustata in silenzio: la `-31`
(«La voce provata da un telefono vero») È la stessa cosa della
`audit-2026-07-31-20` («Provare la voce su telefono»), tuttora aperta. La chiave
nuova viene creata come chiesto, e la sua nota nomina la vecchia: due task per
lo stesso lavoro sono un difetto se nessuno lo sa, non se sta scritto dentro.

Uso:
    EMBER_URL=https://divina.formahub.it ADMIN_TOKEN=... \
        python3 scripts/seed_task_v6_2026_08_01.py
"""
import os
import sys

_K = "audit-2026-08-01-"

# (chiave, titolo, priorità, nota di nascita)
TASK_V6 = [
    # ── Conversazione — l'area ferma a 4/10 ──────────────────────────────────
    (_K + "22", "Il muro diventa una porta", "alta",
     "«Non ho questa informazione nelle aree a cui ho accesso» chiude la "
     "conversazione. Va sostituito con una frase che ammette il buco e offre di "
     "colmarlo, con l'azione di scrittura attaccata alla risposta — non in un "
     "menu altrove."),
    (_K + "23", "Il tono naturale vale per tutti, il contenuto fuori dal vault no", "alta",
     "Saluti, cambio argomento, tornare indietro: per tutti i tenant. Rispondere "
     "con conoscenza generale: solo owner, salvo spunta esplicita sul record del "
     "tenant. Il widget sul sito di un cliente non può inventare sul cliente."),
    (_K + "24", "Ricordare il filo della conversazione", "media",
     "Oggi ogni domanda vive da sola. Tornare su una cosa detta prima («e per "
     "quell'altro cliente?») deve funzionare, soprattutto a voce, dove "
     "riformulare tutto è innaturale."),
    # ── Knowledge base dalle conversazioni ───────────────────────────────────
    (_K + "25", "Le conversazioni propongono note, non le scrivono", "alta",
     "A fine conversazione Divina propone 0-3 «cose imparate», ciascuna con la "
     "citazione del punto da cui viene, nella coda Proposte che già esiste. "
     "Approvate → nota marcata «da conversazione». Mai in automatico."),
    (_K + "26", "Ogni proposta porta la sua fonte", "media",
     "Quale conversazione, quale passaggio. Una nota senza provenienza è una voce "
     "di corridoio, e in un cervello che si vende sulla tracciabilità è un "
     "difetto di prodotto."),
    (_K + "27", "Retention delle conversazioni", "media",
     "Le conversazioni coi clienti SONO dati personali. Finché il motore gira in "
     "US West, tenerne il minimo e per il minor tempo. Serve una politica "
     "scritta, non un default implicito."),
    # ── Estetica e resa visiva — l'area nuova (settima del quadro) ────────────
    (_K + "28", "L'orbita protagonista della home", "alta",
     "Grande, centrale, senza etichette sui nodi. Squadra/Fatte/Contraddizioni "
     "sotto. Colore per agente: Divina giallo, Dante rosso, Virgilio azzurro, "
     "Beatrice com'è, grigio a riposo."),
    (_K + "29", "Il respiro: fermo ≠ rotto", "media",
     "A riposo l'orbita pulsa lentamente. Oggi un cervello che non ha niente da "
     "fare e uno che si è piantato sono indistinguibili a occhio."),
    (_K + "30", "Il colore non basta da solo", "alta",
     "Una riga di testo sotto l'orbita dice sempre quello che dice il colore. Chi "
     "non distingue rosso e azzurro deve capire lo stesso. Non è una rifinitura: "
     "è accessibilità."),
    (_K + "31", "La voce provata da un telefono vero", "media",
     "Gli screenshot a 390 px non sono un pollice su un vetro. Aperta dal 31/07 e "
     "mai mossa. ATTENZIONE: è lo STESSO lavoro della task audit-2026-07-31-20 "
     "(«Provare la voce su telefono»), tuttora aperta — chiudere entrambe insieme."),
    # ── Il metodo ────────────────────────────────────────────────────────────
    (_K + "32", "Il merge mette «da verificare», non chiude", "media",
     "Una PR mergiata sposta le task citate in uno stato intermedio e lo segnala; "
     "diventano «fatta» solo dopo lo sguardo. Il punteggio del quadro e lo "
     "storico possono invece aggiornarsi da soli: sono una media di numeri "
     "scritti a mano, non un giudizio."),
]


def seed(post) -> list[dict]:
    """Idempotente (chiave stabile). `post(path, json) -> dict` è il trasporto:
    urllib in produzione, TestClient nei test — stessa logica, testabile."""
    esiti = []
    for key, titolo, priorita, nota in TASK_V6:
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
        # urllib, non httpx (punto 8, 1/08): uno script di manutenzione deve
        # girare col Python di sistema, senza costruire un ambiente virtuale.
        req = urllib.request.Request(base + path, data=_json.dumps(body).encode(),
                                     headers={"Authorization": f"Bearer {tok}",
                                              "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return _json.loads(r.read().decode())

    for e in seed(post):
        print(f"  {e['key']} · {e['status']} · {e['priorita']} · id={e['id']}")
    print("Seed V6 completato (idempotente: rilanciarlo non duplica).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
