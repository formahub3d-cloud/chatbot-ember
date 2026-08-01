#!/usr/bin/env python3
"""V7/B3 · La parità della console smette di essere una disciplina e diventa un vincolo.

La regola «la console è UNA: `panel/index.html` + `voce.js` + `brain3d.js`
byte-identici nei due repo» è scritta da mesi e finora è stata rispettata a mano,
con `cp` + commit su entrambi. Una disciplina regge finché qualcuno se ne ricorda;
la task `audit-2026-07-31-13` («decidere quale console è quella vera») nasce
proprio dal dubbio che a un certo punto non si siano più ricordati.

**Non decide quale console sia quella vera** — è una scelta di Andrea, e resta
aperta. Rende però impossibile la divergenza SILENZIOSA, con due presìdi che
insieme coprono i due modi reali di sbagliare:

1. **Qualcuno modifica una copia senza passare dalla procedura.** È il caso
   proibito (l'orchestratore si modifica MAI direttamente) ed è quello che
   succede per distrazione. Questo script, in CI di ENTRAMBI i repo, confronta i
   tre file col manifesto `panel/CONSOLE.sha256`: un file toccato senza
   rigenerare il manifesto fa fallire la CI di quel repo, subito.

2. **Un repo viene aggiornato e l'altro no.** Nessuna CI può vederlo da sola
   (i due repo non si leggono a vicenda, e dare un token cross-repo sarebbe un
   prerequisito nuovo — vedi regola 1 del giro). Ma il manifesto è un'identità
   del contenuto: entrambi i servizi la espongono su `/version` come
   `console_sha`, e la console — che parla con tutti e due — confronta le due
   e lo dichiara. La divergenza non si previene lì, si VEDE, che è il massimo
   ottenibile senza segreti nuovi.

Uso:
    python3 scripts/console_parita.py            # verifica (esce 1 se diverge)
    python3 scripts/console_parita.py --scrivi   # rigenera il manifesto

Solo stdlib: gira col Python di sistema, in CI di entrambi i repo, senza venv.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PANEL = ROOT / "panel"
MANIFESTO = PANEL / "CONSOLE.sha256"

# I tre file che DEVONO essere byte-identici nei due repo. `voce.js` ha una sua
# regola in più (si modifica in widget/, non in panel/), ma qui conta solo che le
# due copie coincidano.
FILE = ("index.html", "brain3d.js", "voce.js")


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def calcola() -> dict[str, str]:
    """Hash dei tre file, più l'hash COMPLESSIVO della console.

    Il complessivo è l'identità che i due servizi espongono su `/version`: un
    numero solo da confrontare a occhio fra i due deploy, invece di tre."""
    righe = {n: _sha(PANEL / n) for n in FILE}
    insieme = hashlib.sha256(
        "".join(f"{n}:{righe[n]}\n" for n in FILE).encode("utf-8")
    ).hexdigest()
    return {**righe, "console": insieme}


def rendi(h: dict[str, str]) -> str:
    corpo = "".join(f"{h[n]}  panel/{n}\n" for n in FILE)
    return ("# Parità della console fra i due repo (V7/B3) — generato da\n"
            "# scripts/console_parita.py --scrivi. NON modificare a mano:\n"
            "# se questo file e i tre file sotto non combaciano, la CI è rossa.\n"
            f"{corpo}{h['console']}  console\n")


def leggi() -> dict[str, str]:
    """Il manifesto committato. {} se non c'è (primo giro, o repo non allineato)."""
    if not MANIFESTO.is_file():
        return {}
    out: dict[str, str] = {}
    for riga in MANIFESTO.read_text("utf-8").splitlines():
        riga = riga.strip()
        if not riga or riga.startswith("#"):
            continue
        parti = riga.split()
        if len(parti) == 2:
            out[parti[1].replace("panel/", "")] = parti[0]
    return out


def console_sha() -> str:
    """L'identità della console per `/version`. Stringa vuota se il manifesto non
    c'è: la console mostrerà «—», mai un valore inventato."""
    return leggi().get("console", "")


def verifica() -> list[str]:
    """Elenco (vuoto = tutto bene) dei problemi trovati."""
    mancanti = [n for n in FILE if not (PANEL / n).is_file()]
    if mancanti:
        return [f"manca il file panel/{n}" for n in mancanti]
    atteso, trovato = leggi(), calcola()
    if not atteso:
        return ["manifesto panel/CONSOLE.sha256 assente: rigeneralo con --scrivi"]
    problemi = []
    for n in FILE:
        if atteso.get(n) != trovato[n]:
            problemi.append(
                f"panel/{n} NON combacia col manifesto — se l'hai modificato qui e "
                f"questo è l'orchestratore, la modifica va fatta nel motore e copiata; "
                f"se questo è il motore, rigenera con --scrivi e copia nell'altro repo")
    if atteso.get("console") != trovato["console"] and not problemi:
        problemi.append("l'hash complessivo non combacia: rigenera con --scrivi")
    return problemi


def main() -> int:
    if "--scrivi" in sys.argv:
        h = calcola()
        MANIFESTO.write_text(rendi(h), "utf-8")
        print(f"manifesto scritto: console {h['console'][:12]}")
        print("RICORDA: copia i tre file E questo manifesto nell'altro repo.")
        return 0
    problemi = verifica()
    for p in problemi:
        print(f"PARITÀ CONSOLE · {p}", file=sys.stderr)
    if problemi:
        return 1
    print(f"Parità console ok · {leggi().get('console', '')[:12]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
