#!/usr/bin/env python3
"""P1 (31-07 sera) · Sette task nuove in «Miglioramenti», come DATI.

Secondo seed, NON una modifica del primo: scripts/seed_audit_2026_07_31.py è
già stato eseguito in produzione e deve restare riproducibile com'era.
Stesso metodo: brain_tasks, kind='audit', idempotency_key stabile
(audit-2026-07-31-09 … -15) — rilanciare non duplica niente.

Uso:
    EMBER_URL=https://divina.formahub.it ADMIN_TOKEN=... \
        python3 scripts/seed_audit_2026_07_31_bis.py

Titoli e note così come sono nel piano: già scritti per essere letti.
Tutte nascono DA FARE tranne la 09, IN CORSO (P2, in lavorazione adesso).
"""
import os
import sys

AUDIT_BIS = [
    ("audit-2026-07-31-09",
     "Il barge-in si riazzera a ogni frase invece che a ogni turno",
     "Le finestre «cieca» (350ms) e di apprendimento (900ms) ripartono a ogni "
     "onplaying, cioè a ogni frase. Con frasi da 2s è il 45% del tempo in cui "
     "non si può interrompere; con frasi corte arriva al 75%. Devono misurare "
     "l'inizio del TURNO parlato.",
     True),
    ("audit-2026-07-31-10",
     "La console appare prima di essere cliccabile e non lo dice",
     "Fra quando la pagina si vede e quando risponde ai clic passano secondi "
     "in cui l'utente clicca e non succede niente. Nessun indicatore.",
     False),
    ("audit-2026-07-31-11",
     "Le schede clienti hanno due note a testa",
     "Cinquanta delle 217 marcature si chiudono da fonti pubbliche. "
     "(In corso nel vault, lato Cowork.)",
     False),
    ("audit-2026-07-31-12",
     "Decidere i temi della lente tematica",
     "Cinque o sei tag nel frontmatter. Senza, la lente resta vuota per "
     "scelta. Decisione di Andrea (proposta in docs/lenti-temi-proposta.md).",
     False),
    ("audit-2026-07-31-13",
     "Decidere quale console è quella vera",
     "panel/index.html vive in due repo, tenuto allineato a mano. Ora che "
     "l'orchestratore si deploya di nuovo, le due copie divergono davvero.",
     False),
    ("audit-2026-07-31-14",
     "Portare il calcolo in Europa",
     "Railway è in US West; Supabase è già in Irlanda. Il motore ha anche un "
     "Postgres Railway con volume, che non si sposta di regione: serve un DB "
     "nuovo in UE e una migrazione. Con ANALYTICS_PERSIST attivo lì dentro ci "
     "sono probabilmente le conversazioni.",
     False),
    ("audit-2026-07-31-15",
     "Revocare le chiavi tenant doppione",
     "In api_keys ci sono 11 chiavi con più FORMA duplicate. Prima di darne "
     "una a un cliente esterno va fatta pulizia.",
     False),
]


def seed(post) -> list[dict]:
    """Idempotente (chiave stabile). `post(path, json) -> dict` è il trasporto:
    httpx in produzione, TestClient nei test — stessa logica, testabile."""
    esiti = []
    for key, titolo, nota, in_corso in AUDIT_BIS:
        r = post("/admin/tasks", {"kind": "audit", "title": titolo, "note": nota,
                                  "status": "aperta", "idempotency_key": key})
        t = (r or {}).get("task") or {}
        stato = t.get("status", "?")
        if in_corso and stato == "aperta" and t.get("id"):
            post("/admin/tasks/transition", {"id": t["id"], "to": "in-approvazione"})
            stato = "in-approvazione"
        esiti.append({"key": key, "id": t.get("id"), "status": stato})
    return esiti


def main() -> int:
    import httpx
    base = os.environ.get("EMBER_URL", "http://localhost:8000").rstrip("/")
    tok = os.environ.get("ADMIN_TOKEN", "")
    if not tok:
        print("ADMIN_TOKEN mancante", file=sys.stderr)
        return 2

    def post(path, body):
        r = httpx.post(base + path, json=body,
                       headers={"Authorization": f"Bearer {tok}"}, timeout=30)
        r.raise_for_status()
        return r.json()

    for e in seed(post):
        print(f"  {e['key']} · {e['status']} · id={e['id']}")
    print("Seed bis completato (idempotente: rilanciarlo non duplica).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
