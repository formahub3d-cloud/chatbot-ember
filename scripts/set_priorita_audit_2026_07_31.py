#!/usr/bin/env python3
"""M4 (31-07 sera) · Le priorità delle task audit esistenti, per CHIAVE.

Come i seed e la chiusura: mai per id (cambiano fra ambienti), mai a mano.
A differenza della chiusura, qui NON si crea ciò che manca: la priorità è un
giudizio su una task che esiste — una chiave assente si segnala e si salta.

Il criterio (dal prompt, con una modifica dichiarata sotto):
  ALTA  = blocca il vendere o il capire.
  MEDIA = migliora molto ciò che già funziona.
  BASSA = va fatta, ma dopo.

Nota di conteggio: il prompt dice «le 15 esistenti» ma le chiavi elencate
sono SEDICI (5 alte, 7 medie, 4 basse: 08 e 11 sono due task distinte).
Si assegnano tutte e sedici — segnalato in PR, non aggiustato in silenzio.

Uso:
    EMBER_URL=https://divina.formahub.it ADMIN_TOKEN=... \
        python3 scripts/set_priorita_audit_2026_07_31.py
"""
import os
import sys

_K = "audit-2026-07-31-"
PRIORITA = {
    # ALTA — blocca il vendere o il capire
    _K + "16": "alta",    # conversazione normale
    _K + "17": "alta",    # sei sezioni
    _K + "21": "alta",    # case study da Centioni
    _K + "19": "alta",    # il valore dei cinque clienti (solo Andrea)
    _K + "07": "alta",    # approvazione e fonti in prima fila
    # MEDIA — migliora molto ciò che già funziona
    _K + "05": "media",   # «dimmi cosa sai» dall'indice (già molto migliorata da systemq)
    _K + "06": "media",   # skill nella conversazione
    _K + "08": "media",   # schede clienti (parte console)
    _K + "11": "media",   # schede clienti (parte vault, lato Cowork)
    _K + "18": "media",   # allarme cervello fermo (il banner c'è: resta il lato server)
    _K + "20": "media",   # voce su telefono
    _K + "15": "media",   # chiavi doppione
    # BASSA — va fatta, ma dopo
    _K + "12": "bassa",   # temi (aspetta Andrea)
    _K + "13": "bassa",   # quale console è la vera
    _K + "14": "bassa",   # Europa
    _K + "04": "bassa",   # menu due porte (assorbita dalla 17)
}


def assegna(get, post) -> list[dict]:
    """`get(path) -> dict`, `post(path, json) -> dict`. Idempotente: rilanciare
    riafferma le stesse priorità. Ritorna un esito per chiave."""
    per_chiave = {}
    for stato in ("", "fatta"):        # anche le chiuse: il giudizio resta leggibile
        r = get("/admin/tasks?limit=500" + (f"&status={stato}" if stato else ""))
        for t in (r or {}).get("tasks", []):
            k = t.get("idempotency_key")
            if k:
                per_chiave[k] = t
    esiti = []
    for key, prio in PRIORITA.items():
        t = per_chiave.get(key)
        if not t:
            esiti.append({"key": key, "priorita": prio, "esito": "assente, saltata"})
            continue
        post("/admin/tasks/priorita", {"id": t["id"], "priorita": prio})
        esiti.append({"key": key, "priorita": prio, "esito": "assegnata"})
    return esiti


def main() -> int:
    import httpx
    base = os.environ.get("EMBER_URL", "http://localhost:8000").rstrip("/")
    tok = os.environ.get("ADMIN_TOKEN", "")
    if not tok:
        print("ADMIN_TOKEN mancante", file=sys.stderr)
        return 2
    h = {"Authorization": f"Bearer {tok}"}

    def get(path):
        r = httpx.get(base + path, headers=h, timeout=30)
        r.raise_for_status()
        return r.json()

    def post(path, body):
        r = httpx.post(base + path, json=body, headers=h, timeout=30)
        r.raise_for_status()
        return r.json()

    for e in assegna(get, post):
        print(f"  {e['key']} · {e['priorita']} · {e['esito']}")
    print("Priorità assegnate (idempotente: rilanciare le riafferma).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
