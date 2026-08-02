#!/usr/bin/env python3
"""V8/E2 · Le task il cui lavoro è in produzione e che sono ancora in «DA FARE».

Il difetto, dichiarato da Andrea nel prompt V8: il commit del V6 (`a2fd734`) ha
costruito l'orbita, il colore, il muro-che-diventa-porta e le proposte da
conversazione, e **non ha nominato nessuna di quelle chiavi**. Quelle task sono
rimaste in DA FARE mentre il lavoro girava in produzione da un giorno. L'unica
chiave che quel commit citava era `audit-2026-07-31-20` (la voce da telefono),
che NON era stata fatta: rilanciare l'automazione su quel commit avrebbe
affermato una cosa falsa.

Poi c'è il secondo buco, più ironico: le tre task del V7 (‑06, ‑24, ‑32) sono
rimaste indietro perché il workflow `audit-merge` — scritto proprio per non
perderle — al primo collaudo leggeva nomi di segreti sbagliati ed è uscito
verde a mani vuote. Corretto in PR #50, ma quel merge era già passato.

Questo script ripara l'arretrato **una volta sola**. Da qui in poi lo fa la
regola 3 (ogni commit nomina le chiavi che tocca) insieme al workflow, e questo
file resta come racconto di cosa è successo.

Cosa NON fa: non chiude niente. Le task passano a «da verificare», che è il
massimo che una macchina possa dire — «il codice c'è, adesso guardalo». «Fatta»
resta una parola che scrive una persona, col suo nome, dopo aver guardato.

Idempotente: una task già mossa (o già chiusa) risponde «gia» e resta com'è.

Uso:
    EMBER_URL=https://divina.formahub.it ADMIN_TOKEN=... \
        python3 scripts/da_verificare_arretrati_2026_08_02.py
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request

# (chiave, dove sta il lavoro — perché una persona possa andare a guardare)
ARRETRATI = [
    # ── V6, in produzione dall'1/08 (commit a2fd734, che non le nominò) ─────
    ("audit-2026-08-01-22", "il muro diventa una porta: rag.NO_ANSWER + gap nella "
                            "risposta + l'offerta attaccata alla bolla (panel .gap-offerta)"),
    ("audit-2026-08-01-23", "tono per tutti (rag._TONO_IT, sempre nel system prompt) e "
                            "contenuto fuori dal vault solo con owner o flag `libera`"),
    ("audit-2026-08-01-25", "app/learned.py: da 0 a 3 proposte per conversazione, in coda "
                            "Proposte — non scrive niente"),
    ("audit-2026-08-01-26", "ogni proposta porta la citazione verificata (learned._cita_vera): "
                            "una citazione non ritrovata fa cadere la proposta"),
    ("audit-2026-08-01-28", "la home È l'orbita: grande, centrale, nessuna etichetta sui nodi "
                            "(brain3d labels:'none')"),
    ("audit-2026-08-01-29", "il respiro a riposo (brain3d BREATH_MS/BREATH_AMP): fermo si "
                            "distingue da rotto"),
    ("audit-2026-08-01-30", "una riga di testo sotto l'orbita che dice quello che dice il "
                            "colore (.orb-frase, aria-live) — accessibilità, non rifinitura"),
    # ── V7, in produzione dall'1/08 notte; perse dal primo audit-merge rotto ─
    ("audit-2026-07-31-06", "le capacità si propongono dentro la conversazione: il catalogo "
                            "si legge da /agents, mai duplicato (capCatalogo/capBox)"),
    ("audit-2026-08-01-24", "app/filo.py: la domanda di seguito espansa PRIMA del retrieval, "
                            "memoria server-side opt-in — e un test che prova che non allarga i permessi"),
    ("audit-2026-08-01-32", "il merge mette «da verificare»: braintasks + /admin/tasks/da-merge "
                            "+ .github/workflows/audit-merge.yml"),
]

TITOLO = "Arretrato: lavoro in produzione mai dichiarato dal suo commit"


def sposta(post) -> dict:
    """`post(path, json)->dict`. Usa lo stesso endpoint del workflow: una strada
    sola per arrivare a «da verificare», non due che possono divergere."""
    corpo = {"pr": "", "titolo": TITOLO, "chiavi": [k for k, _ in ARRETRATI],
             "url": ""}
    return post("/admin/tasks/da-merge", corpo) or {}


def main() -> int:
    base = os.environ.get("EMBER_URL", "http://localhost:8000").rstrip("/")
    tok = os.environ.get("ADMIN_TOKEN", "")
    if not tok:
        print("ADMIN_TOKEN mancante", file=sys.stderr)
        return 2

    def post(path, body):
        req = urllib.request.Request(
            base + path, data=json.dumps(body).encode(),
            headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())

    dove = dict(ARRETRATI)
    esiti = sposta(post).get("esiti", [])
    for e in esiti:
        print(f"  {e['chiave']} · {e['esito']}"
              f"{' (' + e['status'] + ')' if e.get('status') else ''}")
        if e.get("esito") == "mossa":
            print(f"      da guardare: {dove.get(e['chiave'], '')}")
    mosse = sum(1 for e in esiti if e.get("esito") == "mossa")
    print(f"\n{mosse} task adesso aspettano uno sguardo. Nessuna è stata chiusa: "
          "«fatta» la scrive una persona, col suo nome.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
