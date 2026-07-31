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


@pytest.mark.skipif(shutil.which("node") is None, reason="node non disponibile")
def test_il_barge_in_non_si_auto_interrompe():
    """C3: soglia RELATIVA all'uscita — con sola eco (nessuna voce umana)
    interrompi() non deve scattare; con la voce vera sì. Logica estratta dai
    marcatori EM_VAD di voce.js: il codice vero, 7 casi simulati."""
    r = subprocess.run(
        ["node", str(ROOT / "scripts" / "test_voce_vad.js")],
        capture_output=True, text=True, timeout=60,
    )
    assert r.returncode == 0, f"VAD KO:\n{r.stdout}\n{r.stderr}"


def test_marcatori_presenti_nel_modulo():
    """Senza marcatori il test node non estrae nulla: guard esplicito.
    U1: il chunker vive nel MOTORE VOCALE UNICO widget/voce.js."""
    src = (ROOT / "widget" / "voce.js").read_text(encoding="utf-8")
    assert "EM_SENTENZE_BEGIN" in src and "EM_SENTENZE_END" in src


def test_motore_vocale_unico_widget_e_console():
    """U1: la console usa LO STESSO modulo del widget. panel/voce.js è la copia
    byte-identica di widget/voce.js (come per la console nei due repo): se
    divergono, qualcuno ha modificato la voce in un posto solo dei due — e
    questo test esplode. Togliere una funzione = toccarla UNA volta + cp."""
    w = (ROOT / "widget" / "voce.js").read_bytes()
    p = (ROOT / "panel" / "voce.js").read_bytes()
    assert w == p, "widget/voce.js e panel/voce.js divergono: ricopiare il modulo"


def test_il_motore_vocale_non_e_duplicato_nella_console():
    """La meccanica della voce NON deve rientrare in panel/index.html: se
    ricompare un chunker o una coda di sintesi lì dentro, U1 è stato disfatto."""
    src = (ROOT / "panel" / "index.html").read_text(encoding="utf-8")
    for vietato in ("EM_SENTENZE_BEGIN", "function emSentenze", "vadTrigger", "function speakPro"):
        assert vietato not in src, f"«{vietato}» è tornato in panel/index.html: la voce va in voce.js"
    src_w = (ROOT / "widget" / "embed.js").read_text(encoding="utf-8")
    for vietato in ("EM_SENTENZE_BEGIN", "function emSentenze", "vadTrigger"):
        assert vietato not in src_w, f"«{vietato}» è tornato in widget/embed.js: la voce va in voce.js"
