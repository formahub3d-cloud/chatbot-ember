"""La voce continua (PR1): il chunker di frasi del widget, testato col codice VERO.

Il chunker vive in widget/embed.js tra i marcatori EM_SENTENZE_BEGIN/END;
scripts/test_voce_sentenze.js lo estrae e lo mette alla prova sui tagli
pericolosi dell'italiano (Dott., S.r.l., art. 3, 1.234,56, elenchi, ellissi,
feed incrementale). Qui lo si esegue dentro la suite, se node è disponibile.
"""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(shutil.which("node") is None, reason="node non disponibile")
def test_chunker_frasi_del_widget():
    r = subprocess.run(
        ["node", str(ROOT / "scripts" / "test_voce_sentenze.js")],
        capture_output=True, text=True, timeout=60,
    )
    assert r.returncode == 0, f"chunker KO:\n{r.stdout}\n{r.stderr}"


def test_marcatori_presenti_nel_widget():
    """Senza marcatori il test node non estrae nulla: guard esplicito."""
    src = (ROOT / "widget" / "embed.js").read_text(encoding="utf-8")
    assert "EM_SENTENZE_BEGIN" in src and "EM_SENTENZE_END" in src
