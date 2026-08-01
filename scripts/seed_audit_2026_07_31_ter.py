#!/usr/bin/env python3
"""X2 (chiusura 31-07) · Sei task nuove in «Miglioramenti», come DATI.

Terzo seed, NON una modifica dei primi due: seed_audit_2026_07_31.py e
seed_audit_2026_07_31_bis.py sono già girati (o stanno per girare) in
produzione e restano riproducibili com'erano. Stesso metodo: brain_tasks,
kind='audit', idempotency_key stabile (audit-2026-07-31-16 … -21) —
rilanciare non duplica niente. Tutte nascono DA FARE.

Uso:
    EMBER_URL=https://divina.formahub.it ADMIN_TOKEN=... \
        python3 scripts/seed_audit_2026_07_31_ter.py
"""
import os
import sys

AUDIT_TER = [
    ("audit-2026-07-31-16",
     "Una conversazione normale, non solo risposte dal cervello",
     "Divina risponde, non conversa: saluti, cambi di argomento, domande "
     "generiche — soprattutto a voce, dove il tono conta più del contenuto. "
     "Vincolo che non si tocca: ciò che viene dal cervello resta citato e "
     "verificabile, la conversazione resta conversazione, e la differenza si "
     "vede. Vale per l'owner e — con perimetro diverso, da decidere — per i "
     "bot cliente: un cliente che saluta e si sente dire «non ho questa "
     "informazione» chiude la finestra."),
    ("audit-2026-07-31-17",
     "Sei sezioni invece di diciannove",
     "Molte sezioni non le apre nessuno: si prende il meglio di ognuna e si "
     "accorpa. Il tuo mondo · Lavora con Divina · Il cervello (Cervello vivo, "
     "Scope, Nodi wiki, Documenti, Contraddizioni) · Miglioramenti "
     "(+Apprendimento, +Segnali) · I companion (Agenti, Regia live, Router) · "
     "Amministrazione (Dashboard, Uso&costi, Eventi, Tenant, Stato&audit). "
     "Nessuna funzione persa: le rotte vecchie portano alla vista nuova."),
    ("audit-2026-07-31-18",
     "Un allarme quando il cervello smette di aggiornarsi",
     "È già successo: tredici giorni di fotografia congelata coi workflow "
     "verdi. Oggi l'età del grafo si vede, ma nessuno avvisa: oltre una "
     "soglia deve dirlo da solo, dove si guarda."),
    ("audit-2026-07-31-19",
     "Il valore economico dei cinque clienti",
     "SOLO ANDREA. È l'unico dato mancante su tutti e cinque i clienti: "
     "senza, non si può sapere quale lavoro rende e quale no."),
    ("audit-2026-07-31-20",
     "Provare la voce su telefono",
     "Tutte le misure di oggi sono da desktop. Il cliente la userà dal "
     "telefono, dove microfono, altoparlante ed eco sono un altro mondo."),
    ("audit-2026-07-31-21",
     "Il case study viene da Centioni, non da ATS",
     "Scoperto oggi: Centioni è l'unico progetto consegnato e online. ATS è "
     "ferma e non ha consegnato nulla. Il materiale di vendita va costruito "
     "su quello che esiste."),
]


def seed(post) -> list[dict]:
    """Idempotente (chiave stabile). `post(path, json) -> dict` è il trasporto:
    urllib in produzione, TestClient nei test — stessa logica, testabile."""
    esiti = []
    for key, titolo, nota in AUDIT_TER:
        r = post("/admin/tasks", {"kind": "audit", "title": titolo, "note": nota,
                                  "status": "aperta", "idempotency_key": key})
        t = (r or {}).get("task") or {}
        esiti.append({"key": key, "id": t.get("id"), "status": t.get("status", "?")})
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
        print(f"  {e['key']} · {e['status']} · id={e['id']}")
    print("Seed ter completato (idempotente: rilanciarlo non duplica).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
