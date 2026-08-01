#!/usr/bin/env python3
"""X1 (chiusura 31-07) · Cinque task audit sono FATTE: qui si chiudono, come DATI.

Le task si cercano per IDEMPOTENCY KEY, mai per id: gli id cambiano fra
ambienti (dev, test, produzione), le chiavi no. La risoluzione chiave→id usa
la dedup di POST /admin/tasks (stessa chiave → ritorna la task esistente con
id e stato reali); se una task non esiste ancora in quell'ambiente, viene
creata col titolo verbatim del seed e poi chiusa — lo stato finale è corretto
comunque, e rilanciare non duplica né riapre nulla.

Ogni chiusura cammina la macchina a stati per la strada che serve
(aperta→fatta; in-approvazione→approvata→in-esecuzione→fatta; …) e lascia
sulla task una NOTA DI CHIUSURA col perché e i numeri misurati: la coda deve
dire la verità anche dopo, non solo cambiare colore.

Uso:
    EMBER_URL=https://divina.formahub.it ADMIN_TOKEN=... \
        python3 scripts/close_audit_2026_07_31.py
    (CLOSED_BY per firmare la chiusura; default 'andrea' — la lancia lui.)

Restano APERTE e questo script NON le tocca: 04, 05, 06, 07, 08, 11, 12,
13, 14, 15 (e le nuove 16-21 del seed ter).
"""
import os
import sys

# (chiave, titolo verbatim del seed — serve solo se la task manca, nota di chiusura)
DA_CHIUDERE = [
    ("audit-2026-07-31-01",
     "Aggiusta l'orb invisibile e il modo vocale che si chiude",
     "FATTA · La voce funziona: provata da Andrea in produzione, arriva in "
     "fondo e non si auto-interrompe. Misurato: prima sillaba dopo 55 ms."),
    ("audit-2026-07-31-02",
     "Un numero solo per un dato solo",
     "FATTA · Home e Cervello vivo dicono entrambi 104, e l'età del grafo "
     "sta accanto al numero."),
    ("audit-2026-07-31-03",
     "Traduci le quarantadue skill in italiano, e chiamale col lavoro che fanno",
     "FATTA · 42 ruoli come frasi-lavoro, reparti e tagline riscritti (non "
     "tradotti). Segnalata a parte: superpowers è un contenitore, non un compito."),
    ("audit-2026-07-31-09",
     "Il barge-in si riazzera a ogni frase invece che a ogni turno",
     "FATTA · Le finestre contano il turno (vout.turnoAt), con i due test "
     "che dimostrano il prima e il dopo."),
    ("audit-2026-07-31-10",
     "La console appare prima di essere cliccabile e non lo dice",
     "FATTA · Numero vero in produzione: 1265 ms (in sandbox erano 78 — la "
     "misura in laboratorio mentiva). Fa fede la riga [boot] in produzione."),
]

# La strada più corta da ogni stato verso 'fatta', dentro TRANSITIONS.
_VERSO_FATTA = {
    "aperta":          ["fatta"],
    "in-approvazione": ["approvata", "in-esecuzione", "fatta"],
    "approvata":       ["in-esecuzione", "fatta"],
    "in-esecuzione":   ["fatta"],
}


def chiudi(post, by: str = "andrea") -> list[dict]:
    """Idempotente. `post(path, json) -> dict` è il trasporto (urllib in
    produzione, TestClient nei test). Ritorna un esito per chiave."""
    esiti = []
    for key, titolo, nota in DA_CHIUDERE:
        r = post("/admin/tasks", {"kind": "audit", "title": titolo,
                                  "status": "aperta", "idempotency_key": key})
        t = (r or {}).get("task") or {}
        tid, stato = t.get("id"), t.get("status", "?")
        if not tid:
            esiti.append({"key": key, "status": stato, "esito": "irrisolvibile"})
            continue
        if stato == "fatta":
            esiti.append({"key": key, "id": tid, "status": "fatta",
                          "esito": "già chiusa"})
            continue
        passi = _VERSO_FATTA.get(stato)
        if passi is None:      # archiviata/fallita: non si forza, si segnala
            esiti.append({"key": key, "id": tid, "status": stato,
                          "esito": "stato terminale, non toccata"})
            continue
        for passo in passi:
            body = {"id": tid, "to": passo, "by": by}
            if passo == "fatta":
                body["note"] = nota      # la nota di chiusura viaggia con la decisione
            post("/admin/tasks/transition", body)
        esiti.append({"key": key, "id": tid, "status": "fatta", "esito": "chiusa"})
    return esiti


def main() -> int:
    import json as _json
    import urllib.request
    base = os.environ.get("EMBER_URL", "http://localhost:8000").rstrip("/")
    tok = os.environ.get("ADMIN_TOKEN", "")
    by = os.environ.get("CLOSED_BY", "andrea")
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

    for e in chiudi(post, by=by):
        print(f"  {e['key']} · {e['status']} · {e['esito']}")
    print("Chiusura completata (idempotente: rilanciare dice solo «già chiusa»).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
