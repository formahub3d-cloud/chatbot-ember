#!/usr/bin/env python3
"""V8/D2 · Una task in priorità ALTA che afferma una cosa falsa.

    audit-2026-07-31-21 · «Il case study viene da Centioni, non da ATS»

Nata il 31/07 da una scoperta parziale, e corretta da Andrea il 1/08: Centioni è
un sito con un piccolo CRM — prova che FORMA consegna lavoro web, **non che
Divina funziona**. E nessuno dei cinque clienti può fare da caso studio, perché
nessuno usa Divina né sa che esiste. L'unico caso studio possibile oggi è l'uso
che ne fa FORMA stessa.

Una task sbagliata in cima all'elenco è peggio di una task assente: chi apre
«Miglioramenti» legge per prima una cosa non vera, e la priorità ALTA gli dice
anche di crederci.

**Cosa fa questo script, e perché così.** Il prompt lascia due strade —
riscriverla o chiuderla con la correzione. Qui si fanno entrambe, perché sono
due cose diverse:

  1. la ‑21 si ARCHIVIA (mai cancella: regola del progetto) con dentro la
     correzione per esteso. Resta leggibile, e chi la ritrova capisce che è
     stata corretta e perché;
  2. nasce la ‑43 col fatto VERO, in priorità media. Il bisogno sotto la task
     sbagliata era reale — serve materiale per vendere — ed è la premessa a
     essere crollata: archiviare e basta avrebbe buttato via anche quello.

Il titolo non si modifica sul posto perché non esiste (di proposito) un modo di
cambiare il testo di una task: una task che cambia parole sotto gli occhi di chi
l'aveva letta è il modo più veloce per non fidarsi più dell'elenco.

La firma è di Andrea perché la correzione l'ha scritta lui, nel prompt V8: non
è una macchina che decide che una cosa è falsa.

Idempotente: rilanciarlo su una ‑21 già archiviata non fa nulla.

Uso:
    EMBER_URL=https://divina.formahub.it ADMIN_TOKEN=... \
        python3 scripts/correggi_case_study_2026_08_02.py
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request

SBAGLIATA = "audit-2026-07-31-21"       # «Il case study viene da Centioni, non da ATS»
NUOVA = "audit-2026-08-02-43"           # il fatto vero, al suo posto
FIRMA = "andrea (correzione scritta nel prompt V8, 02-08)"

NOTA_ARCHIVIO = (
    "ARCHIVIATA PERCHÉ FALSA, non perché fatta. Centioni è un sito con un piccolo "
    "CRM: prova che FORMA consegna lavoro web, NON che Divina funziona. E nessuno "
    "dei cinque clienti può fare da caso studio, perché nessuno usa Divina né sa "
    "che esiste. Correzione di Andrea dell'1/08, applicata il 02-08. Sostituita da "
    f"{NUOVA}, che dice la cosa vera."
)

TITOLO_NUOVA = "L'unico caso studio possibile oggi è FORMA che usa Divina"
NOTA_NUOVA = (
    "Sostituisce " + SBAGLIATA + ", archiviata perché affermava una cosa falsa "
    "(«il case study viene da Centioni»). Il fatto vero: nessuno dei cinque clienti "
    "usa Divina né sa che esiste, quindi nessuno può fare da caso studio. Quello che "
    "esiste davvero è l'uso interno — il cervello, la console, la voce, gli audit — "
    "e va raccontato per quello che è: FORMA che lavora col proprio prodotto. "
    "Priorità media e non alta: serve per vendere, ma non sblocca niente di tecnico, "
    "e il collo di bottiglia su questo fronte è il calendario, non la tastiera."
)


def correggi(get, post) -> dict:
    """`get(path)->dict`, `post(path, json)->dict`. Ritorna il referto."""
    esito = {"archiviata": False, "creata": False, "note": []}
    per_chiave: dict[str, dict] = {}
    for st in ("", "archiviata", "fatta"):
        path = "/admin/tasks?limit=300" + (f"&status={st}" if st else "")
        for t in (get(path) or {}).get("tasks", []):
            if t.get("idempotency_key"):
                per_chiave.setdefault(t["idempotency_key"], t)

    vecchia = per_chiave.get(SBAGLIATA)
    if not vecchia:
        esito["note"].append(f"{SBAGLIATA} non trovata: il seed del 31/07 è mai girato?")
    elif vecchia.get("status") in ("archiviata", "fatta"):
        esito["note"].append(f"{SBAGLIATA} è già {vecchia['status']}: non la si tocca.")
    else:
        post("/admin/tasks/transition", {"id": vecchia["id"], "to": "archiviata",
                                         "by": FIRMA, "note": NOTA_ARCHIVIO})
        esito["archiviata"] = True

    # La creazione è idempotente per chiave: il motore ritorna quella esistente.
    r = post("/admin/tasks", {"kind": "audit", "title": TITOLO_NUOVA, "note": NOTA_NUOVA,
                              "status": "aperta", "priorita": "media",
                              "idempotency_key": NUOVA})
    t = (r or {}).get("task") or {}
    esito["creata"] = not t.get("duplicate")
    esito["nuova_id"] = t.get("id")
    return esito


def main() -> int:
    base = os.environ.get("EMBER_URL", "http://localhost:8000").rstrip("/")
    tok = os.environ.get("ADMIN_TOKEN", "")
    if not tok:
        print("ADMIN_TOKEN mancante", file=sys.stderr)
        return 2
    intest = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}

    def get(path):
        req = urllib.request.Request(base + path, headers=intest)
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())

    def post(path, body):
        req = urllib.request.Request(base + path, data=json.dumps(body).encode(),
                                     headers=intest)
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())

    e = correggi(get, post)
    print(f"  {SBAGLIATA}: {'archiviata (era FALSA)' if e['archiviata'] else 'invariata'}")
    print(f"  {NUOVA}: {'creata' if e['creata'] else 'già esistente'} · id={e.get('nuova_id')}")
    for n in e["note"]:
        print(f"  · {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
