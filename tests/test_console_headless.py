"""M4 · Il controllo che avrebbe evitato tutto: la console si APRE davvero.

I test Python non aprono mai il pannello — «_rec is not defined» l'ha lasciato
morto in produzione senza che nessuno se ne accorgesse. Questo wrapper esegue
scripts/test_console_headless.js (Chromium senza testa, demo, zero rete):
eccezioni in pagina = rosso; modo vocale che non disegna pixel = rosso; modale
che si chiude durante la risposta = rosso.

Dove Playwright/Chromium non ci sono (exit 2) il test SALTA dichiarandolo:
meglio uno skip visibile che una finta copertura. In locale/sandbox:
  NODE_PATH=<node_modules con playwright> python -m pytest tests/test_console_headless.py
"""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(shutil.which("node") is None, reason="node non disponibile")
def test_la_console_si_apre_davvero():
    r = subprocess.run(
        ["node", str(ROOT / "scripts" / "test_console_headless.js")],
        capture_output=True, text=True, timeout=180,
    )
    if r.returncode == 2:
        pytest.skip(f"ambiente senza browser: {r.stderr.strip() or r.stdout.strip()}")
    assert r.returncode == 0, f"console NON viva:\n{r.stdout}\n{r.stderr}"
