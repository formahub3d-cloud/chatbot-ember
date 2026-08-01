#!/usr/bin/env python3
"""Chiusura dell'1/08 · Il giudizio task-per-task di Andrea/Cowork, come DATI.

Stesso stampo di close_audit_2026_07_31.py: per IDEMPOTENCY KEY, mai per id;
idempotente; nota di chiusura firmata che dice PERCHÉ. Tre famiglie:

  FATTE (5)      04 · 05 · 12 · 17 · 19 — verificate nella revisione dell'1/08.
  VISTA E POI (2) 07 · 18 — nel referto risultano fatte ma NON sono state
                 riverificate in produzione: si chiudono SOLO con la conferma
                 esplicita CONFERMA_VISTA=si, dopo i dieci secondi di sguardo
                 al pannello. Meglio dieci secondi che una task chiusa per
                 sentito dire — la 07 riguarda le frasi su cui si vende Divina.
  IN CORSO (2)   11 · 16 — cominciate, non finite: passano a in-approvazione
                 con la nota che dice a che punto sono.

Le sette aperte (06 · 08 · 13 · 14 · 15 · 20 · 21) NON si toccano.
Dopo questo script il conto atteso è: 12 fatte (con la conferma) · 2 in
corso · 7 aperte — e cinque delle sette aperte non dipendono da codice.

Uso:
    EMBER_URL=… ADMIN_TOKEN=… python3 scripts/close_audit_2026_08_01.py
    EMBER_URL=… ADMIN_TOKEN=… CONFERMA_VISTA=si python3 scripts/close_audit_2026_08_01.py
    (CLOSED_BY per firmare; default 'andrea' — lo lancia lui.)
"""
import os
import sys

_K = "audit-2026-07-31-"

# (chiave, titolo verbatim del seed — solo se manca, nota di chiusura)
FATTE = [
    (_K + "04",
     "Dividi il menu in due porte: «lavorare» e «amministrare»",
     "FATTA · Assorbita e superata dalla V2: non due porte ma sei, più "
     "Diagnostica staccata. L'obiettivo era smettere di far scegliere fra "
     "ventuno cose: raggiunto (verificato, 19 viste → 6 porte)."),
    (_K + "05",
     "Fai rispondere «dimmi cosa sai» dall'indice",
     "FATTA · Risponde dai metadati dell'indice, coi buchi dichiarati; i "
     "saluti non trovano più il muro (V2-D). Verificato nel codice: "
     "quadro(grants) usa i grant veri e gli argomenti non visibili tornano "
     "al retrieval."),
    (_K + "12",
     "Decidere i temi della lente tematica",
     "FATTA · Sette temi decisi da Andrea e APPLICATI: tag tema/* su tutte "
     "e 106 le note (1/08, gate verde). Il collegamento della lente è la "
     "task 5 del backlog (re-ingest + tags in /admin/brain/notes)."),
    (_K + "17",
     "Sei sezioni invece di diciannove",
     "FATTA · Con la V2: sei porte + Diagnostica richiudibile, rotte "
     "vecchie funzionanti (verificato)."),
    (_K + "19",
     "Il valore economico dei cinque clienti",
     "FATTA · Dati da Andrea l'1/08, scritti nel vault: ~9.300 EUR/anno "
     "ricorrente + 1.100 EUR una tantum; cinque schede + quadro "
     "portafoglio."),
]

# Chiusura SOLO dopo lo sguardo al pannello (CONFERMA_VISTA=si).
VISTA_E_POI = [
    (_K + "07",
     "Metti in prima fila l'approvazione umana e le fonti",
     "FATTA · Le due frasi in prima fila in Impostazioni, grandi; fonti "
     "sotto ogni risposta. Chiusa DOPO verifica a occhio in produzione "
     "(riguarda le frasi su cui si vende Divina)."),
    (_K + "18",
     "Un allarme quando il cervello smette di aggiornarsi",
     "FATTA · Banner arancione ovunque oltre le 24 ore dall'ultima ingest "
     "(V2-B). Chiusa DOPO verifica a occhio in produzione."),
]

# aperta → in-approvazione, con la nota che dice a che punto è.
IN_CORSO = [
    (_K + "11",
     "Le schede clienti hanno due note a testa",
     "IN CORSO · Stato, servizio, referente e valore scritti l'1/08. "
     "Restano le conferme dai clienti — ferme per scelta di Andrea (non ha "
     "ancora parlato del bot a nessuno)."),
    (_K + "16",
     "Una conversazione normale, non solo risposte dal cervello",
     "IN CORSO · Metà fatta: saluti e domande sul sistema non trovano più "
     "il muro (V2-D). Manca la conversazione vera: cambiare argomento, "
     "tornare indietro, il tono a voce."),
]

_VERSO_FATTA = {
    "aperta":          ["fatta"],
    "in-approvazione": ["approvata", "in-esecuzione", "fatta"],
    "approvata":       ["in-esecuzione", "fatta"],
    "in-esecuzione":   ["fatta"],
}


def _risolvi(post, key, titolo):
    r = post("/admin/tasks", {"kind": "audit", "title": titolo,
                              "status": "aperta", "idempotency_key": key})
    return (r or {}).get("task") or {}


def _chiudi_una(post, t, nota, by):
    passi = _VERSO_FATTA.get(t.get("status"))
    if passi is None:
        return "già chiusa" if t.get("status") == "fatta" else "stato terminale, non toccata"
    for passo in passi:
        body = {"id": t["id"], "to": passo, "by": by}
        if passo == "fatta":
            body["note"] = nota
        post("/admin/tasks/transition", body)
    return "chiusa"


def aggiorna(post, by: str = "andrea", conferma_vista: bool = False) -> list[dict]:
    """Idempotente. `post(path, json) -> dict`. Un esito per chiave."""
    esiti = []
    for key, titolo, nota in FATTE:
        t = _risolvi(post, key, titolo)
        esiti.append({"key": key, "esito": _chiudi_una(post, t, nota, by) if t.get("id") else "irrisolvibile"})
    for key, titolo, nota in VISTA_E_POI:
        t = _risolvi(post, key, titolo)
        if not t.get("id"):
            esiti.append({"key": key, "esito": "irrisolvibile"})
        elif not conferma_vista:
            esiti.append({"key": key, "esito": "IN ATTESA DELLO SGUARDO (rilancia con CONFERMA_VISTA=si dopo aver guardato il pannello)"})
        else:
            esiti.append({"key": key, "esito": _chiudi_una(post, t, nota, by)})
    for key, titolo, nota in IN_CORSO:
        t = _risolvi(post, key, titolo)
        if not t.get("id"):
            esiti.append({"key": key, "esito": "irrisolvibile"})
        elif t.get("status") == "aperta":
            post("/admin/tasks/transition", {"id": t["id"], "to": "in-approvazione", "note": nota})
            esiti.append({"key": key, "esito": "in corso"})
        else:
            esiti.append({"key": key, "esito": f"già {t.get('status')}"})
    return esiti


def main() -> int:
    import json as _json
    import urllib.request
    base = os.environ.get("EMBER_URL", "http://localhost:8000").rstrip("/")
    tok = os.environ.get("ADMIN_TOKEN", "")
    by = os.environ.get("CLOSED_BY", "andrea")
    vista = os.environ.get("CONFERMA_VISTA", "").strip().lower() in ("si", "sì", "1", "true")
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

    for e in aggiorna(post, by=by, conferma_vista=vista):
        print(f"  {e['key']} · {e['esito']}")
    print("Aggiornamento 1/08 completato (idempotente)."
          + ("" if vista else " 07 e 18 aspettano lo sguardo: CONFERMA_VISTA=si."))
    return 0


if __name__ == "__main__":
    sys.exit(main())
