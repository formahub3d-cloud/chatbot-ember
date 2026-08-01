#!/usr/bin/env python3
"""V7/C · Dal messaggio di merge alle task «da verificare».

Legge i messaggi dei commit entrati col merge, ne estrae le chiavi delle task
audit (`audit-AAAA-MM-GG-NN`) e chiede al motore di metterle **da verificare**.

Perché tutti i commit e non solo quello di merge: il messaggio di merge di GitHub
è «Merge pull request #NN …» + il titolo della PR, e basta. Le chiavi citate nel
corpo della PR o nei singoli commit non ci sarebbero — cioè quasi sempre.

Quello che NON fa, ed è il punto: non chiude niente. «Fatta» resta una parola
che scrive una persona, col suo nome, dopo aver guardato. Il merge dice soltanto
«il codice c'è, adesso guardala».

Perché le CHIAVI e non gli id: gli id delle task cambiano fra ambienti (dev,
staging, produzione), le chiavi di idempotenza no. È la stessa scelta degli
script di chiusura del 31-07 e dell'1-08.

Uso (in CI, dal workflow audit-merge.yml):
    EMBER_URL=… ADMIN_TOKEN=… MSG="…" python3 scripts/audit_da_merge.py

Solo stdlib e `urllib`, MAI httpx: gira col Python di sistema, senza venv
(regola dell'1/08).
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request

# `audit-2026-08-01-32`, `audit-2026-07-31-07`: il formato usato dai seed.
CHIAVE = re.compile(r"\baudit-\d{4}-\d{2}-\d{2}-\d{1,3}\b")


def chiavi_da(testo: str) -> list[str]:
    """Le chiavi citate, in ordine di apparizione e senza doppioni.

    Si guarda TUTTO il messaggio (titolo + corpo del merge, che su GitHub
    contiene anche il titolo della PR): chi scrive una PR nomina la task dove gli
    viene comodo, e un'automazione che pretende un posto preciso non la usa
    nessuno."""
    viste, out = set(), []
    for m in CHIAVE.findall(testo or ""):
        if m not in viste:
            viste.add(m)
            out.append(m)
    return out


def pr_da(testo: str) -> str:
    """Il numero di PR dal messaggio di merge di GitHub («Merge pull request #48»)."""
    m = re.search(r"Merge pull request #(\d+)", testo or "")
    return f"#{m.group(1)}" if m else ""


def titolo_da(testo: str) -> str:
    """Il titolo della PR: su GitHub è la terza riga del messaggio di merge;
    su un merge locale (o squash) è la prima. Si prende la prima riga NON vuota
    che non sia l'intestazione automatica."""
    for riga in (testo or "").splitlines():
        r = riga.strip()
        if r and not r.startswith("Merge pull request") and not r.startswith("Merge branch"):
            return r[:120]
    return ""


def main() -> int:
    base = os.environ.get("EMBER_URL", "").strip().rstrip("/")
    tok = os.environ.get("ADMIN_TOKEN", "").strip()
    msg = os.environ.get("MSG", "")
    if not base or not tok:
        # Un'automazione di contorno non tinge di rosso un merge sano: si
        # dichiara e si esce bene. Il segnale è il log, non la pipeline rotta.
        print("EMBER_URL/ADMIN_TOKEN non configurati: niente da fare.")
        return 0
    chiavi = chiavi_da(msg)
    if not chiavi:
        print("Nessuna task audit citata nel merge: niente da aggiornare.")
        return 0
    corpo = {"pr": pr_da(msg), "titolo": titolo_da(msg), "chiavi": chiavi,
             "url": (os.environ.get("REPO_URL", "").strip() + "/commit/"
                     + os.environ.get("SHA", "").strip()[:12]) if os.environ.get("SHA") else ""}
    req = urllib.request.Request(
        base + "/admin/tasks/da-merge", data=json.dumps(corpo).encode(),
        headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            esito = json.loads(r.read().decode())
    except urllib.error.URLError as e:
        print(f"Motore non raggiungibile ({e}): le task restano dove sono.", file=sys.stderr)
        return 0            # di nuovo: non si rompe un merge per questo
    for e in esito.get("esiti", []):
        print(f"  {e['chiave']} · {e['esito']}{' (' + e['status'] + ')' if e.get('status') else ''}")
    print("Il merge NON chiude le task: adesso aspettano uno sguardo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
