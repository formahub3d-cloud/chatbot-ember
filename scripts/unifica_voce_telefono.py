#!/usr/bin/env python3
"""V7/C · Il doppione della voce su telefono: una sopravvive, l'altra si archivia.

`audit-2026-08-01-31` («La voce provata da un telefono vero») e
`audit-2026-07-31-20` («Provare la voce su telefono») sono **lo stesso lavoro**.
L'errore è dichiarato nel prompt V7 da chi l'ha fatto: una task riscritta poche
ore dopo averla già elencata.

Quale sopravvive: la **-20**, la più vecchia. Non per anzianità in sé, ma perché
il fatto che conta su quella task è *da quanto tempo è ferma* — «aperta dal 31/07
e mai mossa» è un'informazione che vive nella sua data di nascita e che
archiviando lei si perderebbe. La -31 si archivia (mai cancella: regola del
progetto) nominando la gemella, così chi la ritrova sa dove guardare.

Idempotente: rilanciarlo su una -31 già archiviata non fa nulla.

Uso:
    EMBER_URL=https://divina.formahub.it ADMIN_TOKEN=… \\
        python3 scripts/unifica_voce_telefono.py
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request

SOPRAVVIVE = "audit-2026-07-31-20"      # «Provare la voce su telefono» (31/07)
ARCHIVIA = "audit-2026-08-01-31"        # «La voce provata da un telefono vero» (01/08)

NOTA_ARCHIVIO = (
    f"Doppione di {SOPRAVVIVE} («Provare la voce su telefono»), che resta aperta ed è "
    "quella da chiudere: è lì che si vede da quanto tempo il lavoro è fermo. "
    "Archiviata l'01/08 dal giro V7, non cancellata."
)
NOTA_SUPERSTITE = (
    f"Unificata con {ARCHIVIA} (stessa cosa, riscritta per errore l'01/08). "
    "La prova non si può automatizzare: serve un pollice su un vetro."
)


def unifica(get, post) -> dict:
    """`get(path)->dict`, `post(path, json)->dict`. Ritorna il referto."""
    esito = {"archiviata": False, "annotata": False, "note": []}
    tutte = (get("/admin/tasks?limit=300") or {}).get("tasks", [])
    per_chiave = {t.get("idempotency_key"): t for t in tutte if t.get("idempotency_key")}
    # anche le chiuse: la -31 potrebbe essere già archiviata da un giro precedente
    for st in ("archiviata", "fatta"):
        for t in (get(f"/admin/tasks?status={st}&limit=300") or {}).get("tasks", []):
            per_chiave.setdefault(t.get("idempotency_key"), t)

    doppia = per_chiave.get(ARCHIVIA)
    if not doppia:
        esito["note"].append(f"{ARCHIVIA} non trovata: forse il seed V6 non è ancora girato.")
    elif doppia.get("status") == "archiviata":
        esito["note"].append(f"{ARCHIVIA} già archiviata: niente da fare.")
    else:
        post("/admin/tasks/transition", {"id": doppia["id"], "to": "archiviata",
                                         "by": "unifica-doppione (V7)", "note": NOTA_ARCHIVIO})
        esito["archiviata"] = True

    viva = per_chiave.get(SOPRAVVIVE)
    if not viva:
        esito["note"].append(f"{SOPRAVVIVE} non trovata: controlla il seed del 31/07.")
    elif viva.get("status") in ("fatta", "archiviata"):
        esito["note"].append(f"{SOPRAVVIVE} è già {viva['status']}: non la si tocca.")
    elif NOTA_SUPERSTITE[:40] in (viva.get("note") or ""):
        esito["note"].append(f"{SOPRAVVIVE} già annotata: niente da fare.")
    else:
        # Una NOTA, non una transizione: sulla superstite non è successo niente —
        # ha solo guadagnato un riferimento. Una transizione finta sporcherebbe
        # la sua storia con un movimento mai avvenuto.
        post("/admin/tasks/nota", {"id": viva["id"], "note": NOTA_SUPERSTITE})
        esito["annotata"] = True
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

    e = unifica(get, post)
    print(f"  {ARCHIVIA}: {'archiviata' if e['archiviata'] else 'invariata'}")
    print(f"  {SOPRAVVIVE}: {'annotata' if e['annotata'] else 'invariata'}")
    for n in e["note"]:
        print(f"  · {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
