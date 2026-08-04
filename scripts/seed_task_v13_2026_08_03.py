#!/usr/bin/env python3
"""V13 (3-08) · Le task del giro «la prima porta», come DATI.

Decimo seed, stesso stampo: brain_tasks, kind='audit', idempotency_key stabile
(`audit-2026-08-03-72` … `-77`). Rilanciarlo non duplica.

**Va lanciato PRIMA del merge**: `audit-merge` legge le chiavi citate nei commit.
"""
import os
import sys

_K = "audit-2026-08-03-"

TASK_V13 = [
    (_K + "72", "La prima porta chiede una cosa sola, non sei", "alta",
     "Il 3/08 il browser ha dimenticato le credenziali e la console si è aperta chiedendo "
     "URL motore, admin token, chiave tenant, URL orchestratore, token orchestratore e "
     "tenant code: sei campi, due dei quali segreti, prima di vedere qualunque cosa. Per "
     "chi conosce il sistema è mezzo minuto; per «l'imprenditore appena partito» del "
     "criterio del V11 è un muro — ed è l'unica porta che quel criterio non aveva mai "
     "incontrato, oltre a essere la prima che si apre. Non è un difetto del V11: quella "
     "finestrella è nata quando il pannello lo usava una persona sola."),
    (_K + "73", "Si guarda Divina prima di collegarla", "alta",
     "La modalità demo esisteva già ma era una spunta in fondo a sei campi: si poteva "
     "guardare Divina solo dopo aver deciso di collegarla. Il percorso era muro → sei "
     "campi → forse qualcosa; deve essere qualcosa → capisco → collego."),
    (_K + "74", "Creare un accesso cliente non passa da una chiave incollata", "alta",
     "Il modulo chiedeva «il VALORE della chiave tenant (ovy_… / ember_…), non il nome», "
     "con la nota «si vede UNA sola volta». Quindi: emetti la chiave, copiala al volo, "
     "incollala in un altro modulo — tre passaggi in cui un segreto passa per gli appunti "
     "e per lo schermo. Adesso si indica il cliente e la chiave nasce sul server, senza "
     "che nessuno la veda: meno passaggi e meno superficie sono la stessa cosa."),
    (_K + "75", "I campi dell'orchestratore vanno sotto «avanzate»", "media",
     "L'orchestratore vive nello stesso progetto, ha un indirizzo noto e il suo token sta "
     "già sul server: non c'è motivo di chiederli a chi apre il pannello. Restano per "
     "un'installazione separata o un collaudo su un altro ambiente, dietro un cassetto "
     "chiuso — non nella prima cosa che si vede."),
    (_K + "76", "Il percorso del cliente percorso da una persona, su dati veri", "alta",
     "Il guardiano lo cammina a ogni push (registra → legge il sito → coda → il cliente la "
     "vede), ma su fixture di demo: prova il cablaggio, non la produzione. Quello che "
     "manca è che lo percorra una persona, con dati veri, senza sapere cosa aspettarsi. Se "
     "in mezzo serve un'istruzione esterna — «adesso copia questo», «adesso vai lì» — quel "
     "passaggio non è finito, e va elencato invece di essere compensato a voce. Il primo "
     "cliente su cui provarlo resta ATS."),
    (_K + "77", "La domanda di seguito su HRH restituisce la cifra", "media",
     "La correzione del V12 su _ANAFORA va riprovata sul filo reale, non dai test: "
     "«Parlami del cliente HRH» → «E quanto paga al mese?» deve contenere 200 €/mese. "
     "Prima del redeploy di Railway fallirebbe ancora e sembrerebbe che la correzione non "
     "funzioni."),
]


def seed(post) -> list[dict]:
    """Idempotente (chiave stabile). `post(path, json) -> dict` è il trasporto."""
    esiti = []
    for key, titolo, priorita, nota in TASK_V13:
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
    print("Seed V13 completato (idempotente: rilanciarlo non duplica).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
