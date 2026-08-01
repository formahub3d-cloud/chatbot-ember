"""V7/B · Le sorprese dell'1/08 non si ripetono.

L'affidabilità è l'area più alta del quadro (9/10) e stanotte ha mostrato la sua
crepa: il sistema è ben testato e non sapeva dire cosa gli mancava. Quattro
migrazioni applicate a mano, ognuna scoperta da un 500 o da un degrado
silenzioso, ore dopo il merge.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

from app import dbcheck
from app.config import settings

ROOT = Path(__file__).resolve().parents[1]


# ══════════════════════════════════════════════════════════════════════════
# B1 · Il motore dichiara quali tabelle si aspetta
# ══════════════════════════════════════════════════════════════════════════
def test_ogni_attesa_dice_cosa_si_rompe_e_dove_sta_il_ddl():
    """«manca ingest_meta» non aiuta nessuno; «manca ingest_meta: l'allarme sui
    commit è cieco» dice se ci si può convivere fino a domani."""
    assert len(dbcheck.ATTESE) >= 12
    for tabella, colonna, ddl, rompe in dbcheck.ATTESE:
        assert tabella and ddl.startswith("db/") and len(rompe) > 25, tabella
        assert (ROOT / ddl).is_file(), f"{ddl} citato ma inesistente"


def test_le_quattro_migrazioni_di_stanotte_sono_tutte_dichiarate():
    """Sono i quattro casi VERI: se un domani una di queste sparisse dall'elenco,
    il guasto tornerebbe a essere invisibile."""
    voci = {(t, c) for t, c, _d, _r in dbcheck.ATTESE}
    assert ("tenant_flags", None) in voci
    assert ("tenant_flags", "libera") in voci        # era una alter table: la colonna
    assert ("ingest_meta", None) in voci
    assert ("key_usage", None) in voci


def test_senza_database_non_si_dichiara_tutto_mancante(monkeypatch):
    """«Non c'è un database» è una CONFIGURAZIONE, non un guasto: va detta con
    parole diverse, altrimenti il pannello urla per niente in sviluppo."""
    monkeypatch.setattr(settings, "grants_backend", "static")
    s = dbcheck.stato()
    assert s["persist"] is False and s["ok"] is False
    assert s["mancanti"] == []                       # NON «manca tutto»
    assert "nessun database" in s["errore"]
    assert "nessun database" in dbcheck.riga_boot()


def test_schema_illeggibile_non_e_uno_schema_a_posto(monkeypatch):
    """«Non ho potuto guardare» non è «va tutto bene»: sono due cose diverse."""
    monkeypatch.setattr(settings, "grants_backend", "supabase")
    monkeypatch.setattr(settings, "database_url", "postgres://x/y")
    monkeypatch.setattr(dbcheck, "_trovate",
                        lambda: (_ for _ in ()).throw(OSError("pooler giù")))
    s = dbcheck.stato()
    assert s["ok"] is False and s["mancanti"] == [] and "non leggibile" in s["errore"]
    assert "NON verificato" in dbcheck.riga_boot()


def test_elenca_solo_quello_che_manca_davvero(monkeypatch):
    monkeypatch.setattr(settings, "grants_backend", "supabase")
    monkeypatch.setattr(settings, "database_url", "postgres://x/y")
    tabelle = {t for t, c, _d, _r in dbcheck.ATTESE}
    colonne = {(t, c) for t, c, _d, _r in dbcheck.ATTESE if c and not c.startswith("@check:")}
    check = {(t, f"@check:CHECK (status = ANY (ARRAY['da-verificare'::text]))")
             for t, c, _d, _r in dbcheck.ATTESE if c and c.startswith("@check:")}
    monkeypatch.setattr(dbcheck, "_trovate", lambda: (tabelle, colonne | check))
    assert dbcheck.stato()["ok"] is True
    # ora si toglie SOLO la colonna `libera`: la tabella c'è, il guasto è la colonna
    monkeypatch.setattr(dbcheck, "_trovate",
                        lambda: (tabelle, (colonne - {("tenant_flags", "libera")}) | check))
    s = dbcheck.stato()
    assert [m["colonna"] for m in s["mancanti"]] == ["libera"]
    assert "conoscenza generale" in s["mancanti"][0]["rompe"]
    assert "tenant_flags.libera" in dbcheck.riga_boot()


def test_riconosce_un_check_non_aggiornato(monkeypatch):
    """Il caso di `da-verificare`: la tabella e le colonne ci sono tutte, ma il
    CHECK non ammette il valore nuovo — e senza questo controllo sarebbe verde."""
    monkeypatch.setattr(settings, "grants_backend", "supabase")
    monkeypatch.setattr(settings, "database_url", "postgres://x/y")
    tabelle = {t for t, c, _d, _r in dbcheck.ATTESE}
    colonne = {(t, c) for t, c, _d, _r in dbcheck.ATTESE if c and not c.startswith("@check:")}
    vecchio = {("brain_tasks", "@check:CHECK (status = ANY (ARRAY['aperta'::text, 'fatta'::text]))")}
    monkeypatch.setattr(dbcheck, "_trovate", lambda: (tabelle, colonne | vecchio))
    s = dbcheck.stato()
    assert len(s["mancanti"]) == 1
    assert s["mancanti"][0]["ddl"] == "db/brain_tasks_da_verificare.sql"


# ══════════════════════════════════════════════════════════════════════════
# B3 · La parità della console è un vincolo, non una disciplina
# ══════════════════════════════════════════════════════════════════════════
def _parita():
    spec = importlib.util.spec_from_file_location(
        "console_parita", ROOT / "scripts" / "console_parita.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules["console_parita"] = m
    spec.loader.exec_module(m)
    return m


def test_il_manifesto_committato_combacia_coi_file_veri():
    """È il controllo che gira in CI di ENTRAMBI i repo: un file toccato senza
    passare dalla procedura di copia rende rossa la CI di quel repo, subito."""
    assert _parita().verifica() == []


def test_un_file_modificato_fa_fallire_la_verifica(tmp_path, monkeypatch):
    m = _parita()
    finta = tmp_path / "panel"
    finta.mkdir()
    for n in m.FILE:
        (finta / n).write_text("originale", "utf-8")
    monkeypatch.setattr(m, "PANEL", finta)
    monkeypatch.setattr(m, "MANIFESTO", finta / "CONSOLE.sha256")
    (finta / "CONSOLE.sha256").write_text(m.rendi(m.calcola()), "utf-8")
    assert m.verifica() == []
    (finta / "index.html").write_text("qualcuno mi ha toccato", "utf-8")
    problemi = m.verifica()
    assert len(problemi) == 1 and "index.html" in problemi[0]


def test_senza_manifesto_si_dice_invece_di_passare(tmp_path, monkeypatch):
    m = _parita()
    finta = tmp_path / "panel"
    finta.mkdir()
    for n in m.FILE:
        (finta / n).write_text("x", "utf-8")
    monkeypatch.setattr(m, "PANEL", finta)
    monkeypatch.setattr(m, "MANIFESTO", finta / "CONSOLE.sha256")
    assert m.verifica() and "manifesto" in m.verifica()[0]
    assert m.console_sha() == ""          # mai un valore inventato


def test_l_identita_e_una_sola_e_cambia_col_contenuto(tmp_path, monkeypatch):
    """È il numero che i due servizi espongono su /version: se differisce, una
    delle due console è vecchia."""
    m = _parita()
    finta = tmp_path / "panel"
    finta.mkdir()
    for n in m.FILE:
        (finta / n).write_text("uguale", "utf-8")
    monkeypatch.setattr(m, "PANEL", finta)
    prima = m.calcola()["console"]
    assert m.calcola()["console"] == prima              # stabile
    (finta / "brain3d.js").write_text("diverso", "utf-8")
    assert m.calcola()["console"] != prima              # sensibile al contenuto


def test_il_motore_espone_l_identita_della_console():
    from app import main
    assert main.version()["console_sha"] == _parita().calcola()["console"]
