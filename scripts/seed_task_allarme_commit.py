#!/usr/bin/env python3
"""Punto 9 (1/08 sera) · Task NUOVA: l'allarme confronta i commit, non le ore.

La task 18 resta chiusa — l'allarme sulle 24 ore esiste ed era quanto chiesto.
Ma l'1/08 alle 14:35 il vault era avanti di UN COMMIT (1f73289, i punteggi
nuovi) e tutto era verde, perché 6 ore sono meno di 24. Il tempo è
un'approssimazione della freschezza; il confronto fra i due commit È la
freschezza. Questa è la task di quel confronto — e l'implementazione viaggia
nella stessa PR (V5b): vault_commit vs commit dell'ultima ingest
(ingest_meta), le ore restano come riserva quando i commit non si leggono.

Idempotente (idempotency_key), come i seed dell'audit. La chiusura chiede lo
sguardo: CONFERMA_VISTA=si dopo aver visto in produzione la riga
«cervello <commit> · vault <commit>» nel Cervello vivo — meglio dieci secondi
che una task chiusa per sentito dire.

urllib, non httpx (punto 8): gira col Python di sistema.

Uso:
    EMBER_URL=… ADMIN_TOKEN=… python3 scripts/seed_task_allarme_commit.py
    EMBER_URL=… ADMIN_TOKEN=… CONFERMA_VISTA=si python3 scripts/seed_task_allarme_commit.py chiudi
"""
import os
import sys

KEY = "allarme-commit-2026-08-01"
TITOLO = "L'allarme del cervello confronta i commit, non le ore"
NOTA_APERTURA = ("Nata guardando il pannello l'1/08: vault avanti di un commit, "
                 "nessun allarme perché 6h < 24h. La domanda utile: il cervello "
                 "ha letto l'ULTIMA versione del vault? vault_info() espone già "
                 "entrambi i numeri — va fatto il confronto.")
NOTA_CHIUSURA = ("FATTA · L'allarme confronta vault_commit con il commit "
                 "dell'ultima ingest (ingest_meta, V5b): diversi = allarme anche "
                 "a 6 ore, uguali = verde. Le ore restano come riserva quando i "
                 "commit non si leggono. Verificata a occhio in produzione "
                 "(riga «cervello · vault» nel Cervello vivo).")

_VERSO_FATTA = {
    "aperta":          ["fatta"],
    "in-approvazione": ["approvata", "in-esecuzione", "fatta"],
    "approvata":       ["in-esecuzione", "fatta"],
    "in-esecuzione":   ["fatta"],
}


def aggiorna(post, chiudi: bool = False, by: str = "andrea") -> str:
    """Idempotente; `post(path, json) -> dict` è il trasporto (urllib in
    produzione, TestClient nei test)."""
    r = post("/admin/tasks", {"kind": "audit", "title": TITOLO, "note": NOTA_APERTURA,
                              "status": "aperta", "priorita": "alta",
                              "idempotency_key": KEY})
    t = (r or {}).get("task") or {}
    if not t.get("id"):
        return "irrisolvibile"
    if not chiudi:
        return f"seminata ({t.get('status')})"
    passi = _VERSO_FATTA.get(t.get("status"))
    if passi is None:
        return "già chiusa" if t.get("status") == "fatta" else "stato terminale, non toccata"
    for passo in passi:
        body = {"id": t["id"], "to": passo, "by": by}
        if passo == "fatta":
            body["note"] = NOTA_CHIUSURA
        post("/admin/tasks/transition", body)
    return "chiusa"


def main() -> int:
    import json as _json
    import urllib.request
    base = os.environ.get("EMBER_URL", "http://localhost:8000").rstrip("/")
    tok = os.environ.get("ADMIN_TOKEN", "")
    by = os.environ.get("CLOSED_BY", "andrea")
    vista = os.environ.get("CONFERMA_VISTA", "").strip().lower() in ("si", "sì", "1", "true")
    cmd = (sys.argv[1] if len(sys.argv) > 1 else "semina").strip().lower()
    if not tok:
        print("ADMIN_TOKEN mancante", file=sys.stderr)
        return 2
    if cmd == "chiudi" and not vista:
        print("La chiusura chiede lo sguardo: guarda nel Cervello vivo la riga "
              "«cervello <commit> · vault <commit>», poi rilancia con CONFERMA_VISTA=si.",
              file=sys.stderr)
        return 1

    def post(path, body):
        # urllib, non httpx (punto 8, 1/08): uno script di manutenzione deve
        # girare col Python di sistema, senza costruire un ambiente virtuale.
        req = urllib.request.Request(base + path, data=_json.dumps(body).encode(),
                                     headers={"Authorization": f"Bearer {tok}",
                                              "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return _json.loads(r.read().decode())

    print(f"  {KEY} · {aggiorna(post, chiudi=(cmd == 'chiudi'), by=by)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
