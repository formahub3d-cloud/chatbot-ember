"""V5b · Il reset delle chiavi (1/08): la logica pura del piano.

Il pezzo che NON deve sbagliare: `revoca` si rifiuta finché la chiave FORMA
nuova non esiste attiva — revocare prima di sostituire chiude Andrea fuori
dalla console (la chiave vive in localStorage `dv_tenant_key`).
"""
import importlib.util
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "reset_chiavi", Path(__file__).resolve().parents[1] / "scripts" / "reset_chiavi.py")
mod = importlib.util.module_from_spec(spec)
sys.modules["reset_chiavi"] = mod
spec.loader.exec_module(mod)

NUOVO = mod.NUOVO_NOME


def test_senza_la_chiave_nuova_il_reset_si_rifiuta():
    chiavi = [{"name": "ATS · Al Tuo Servizio", "active": True},
              {"name": "FORMA (interno)", "active": True}]
    p = mod.piano_reset(chiavi)
    assert p["pronto"] is False and "emetti" in p["motivo"]
    # il piano elenca comunque cosa VERREBBE revocato: si legge prima di agire
    assert p["revoca"] == ["ATS · Al Tuo Servizio", "FORMA (interno)"]


def test_con_la_nuova_attiva_si_revoca_tutto_il_resto_ma_non_lei():
    chiavi = [{"name": "ATS · Al Tuo Servizio", "active": True},
              {"name": "FORMA (interno)", "active": True},
              {"name": "Andrea Aloia", "active": False},      # già spenta: non si ritocca
              {"name": NUOVO, "active": True}]
    p = mod.piano_reset(chiavi)
    assert p["pronto"] is True and p["motivo"] == ""
    assert NUOVO not in p["revoca"]
    assert p["revoca"] == ["ATS · Al Tuo Servizio", "FORMA (interno)"]


def test_la_nuova_spenta_non_basta_e_i_nomi_doppi_contano_una_volta():
    # più chiavi con lo stesso nome (la revoca è per nome) → una voce sola;
    # la chiave nuova REVOCATA non sblocca niente: serve attiva.
    chiavi = [{"name": "ATS · Al Tuo Servizio", "active": True},
              {"name": "ATS · Al Tuo Servizio", "active": True},
              {"name": NUOVO, "active": False}]
    p = mod.piano_reset(chiavi)
    assert p["pronto"] is False
    assert p["revoca"] == ["ATS · Al Tuo Servizio"]
