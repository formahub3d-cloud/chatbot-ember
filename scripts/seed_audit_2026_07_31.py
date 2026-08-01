#!/usr/bin/env python3
"""M2 · Le otto task dell'audit del pannello (31-07-2026), come DATI.

Una lista scritta nel codice invecchia in silenzio — è il modo in cui il
cervello è rimasto fermo tredici giorni senza che nessuno se ne accorgesse.
Queste otto righe entrano in `brain_tasks` (kind='audit') con una
`idempotency_key` STABILE ciascuna: rilanciare il seed non duplica niente,
e la sezione «Miglioramenti» resta viva mentre il lavoro procede.

Uso (contro il motore in produzione o in locale):
    EMBER_URL=https://divina.formahub.it ADMIN_TOKEN=... \
        python3 scripts/seed_audit_2026_07_31.py

La 01 nasce IN CORSO (in-approvazione: è in lavorazione adesso, M4 in PR);
le altre nascono DA FARE (aperte). I titoli sono quelli dell'audit,
già scritti per essere letti: NON riformulati.
"""
import os
import sys

# (chiave stabile, titolo DELL'AUDIT, nota, nasce in corso?)
AUDIT_2026_07_31 = [
    ("audit-2026-07-31-01",
     "Aggiusta l'orb invisibile e il modo vocale che si chiude",
     "Sono due guasti, non due opinioni, e riguardano la funzione più vistosa "
     "del prodotto. Finché la sfera non si vede, tutto il lavoro sulla voce è invisibile.",
     True),
    ("audit-2026-07-31-02",
     "Un numero solo per un dato solo",
     "100 contro 104 va chiuso alla radice: il conteggio si calcola in un posto e "
     "tutte le schermate leggono quello. Insieme, l'età del dato va portata dove "
     "si guarda, non a piè di pagina.",
     False),
    ("audit-2026-07-31-03",
     "Traduci le quarantadue skill in italiano, e chiamale col lavoro che fanno",
     "Miglior rapporto fra effetto e fatica: non tocca il codice, cambia "
     "completamente a chi sembra rivolto il prodotto. «Sollecita le fatture in "
     "ritardo», non «Debt Chaser».",
     False),
    ("audit-2026-07-31-04",
     "Dividi il menu in due porte: «lavorare» e «amministrare»",
     "Cinque o sei voci davanti. Tutto il resto dietro una voce sola. Non si "
     "cancella niente: si smette di chiedere all'utente di scegliere fra ventuno "
     "cose per farne una.",
     False),
    ("audit-2026-07-31-05",
     "Fai rispondere «dimmi cosa sai» dall'indice",
     "È la prima domanda che fa chiunque, e oggi è la peggiore risposta che dà. "
     "Non è taratura del recupero: è una risposta diversa, costruita sui metadati.",
     False),
    ("audit-2026-07-31-06",
     "Porta le skill dentro la conversazione",
     "Le capacità si propongono nel punto in cui servono, invece di vivere in un "
     "catalogo che bisogna ricordarsi di aprire.",
     False),
    ("audit-2026-07-31-07",
     "Metti in prima fila l'approvazione umana e le fonti",
     "Sono i due motivi per cui qualcuno sceglierebbe Divina invece di un "
     "assistente qualunque, e oggi sono le due cose scritte più piccole.",
     False),
    ("audit-2026-07-31-08",
     "Riempi le schede clienti prima di mostrarlo a un cliente",
     "Due note per cliente si vedono adesso, dalle orbite. Cinquanta delle 217 "
     "marcature si chiudono cercando su fonti pubbliche.",
     False),
]


def seed(post) -> list[dict]:
    """Semina le 8 task. `post(path, json) -> dict` è il trasporto (urllib in
    produzione, TestClient nei test): la logica resta identica e testabile.
    Idempotente: la chiave stabile fa da guardia, il rilancio non duplica."""
    esiti = []
    for key, titolo, nota, in_corso in AUDIT_2026_07_31:
        r = post("/admin/tasks", {"kind": "audit", "title": titolo, "note": nota,
                                  "status": "aperta", "idempotency_key": key})
        t = (r or {}).get("task") or {}
        stato = t.get("status", "?")
        if in_corso and stato == "aperta" and t.get("id"):
            # la 01 è in lavorazione ADESSO (M4 in questa PR): entra nel gruppo
            # IN CORSO tramite la macchina a stati, non con uno stato inventato.
            post("/admin/tasks/transition", {"id": t["id"], "to": "in-approvazione"})
            stato = "in-approvazione"
        esiti.append({"key": key, "id": t.get("id"), "status": stato})
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
    print("Seed completato (idempotente: rilanciarlo non duplica).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
