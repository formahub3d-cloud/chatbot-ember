"""Test del write-back generico (render/save note) contro un vault temporaneo.
Verifica slug sicuro, cartella derivata dallo scope, facet e conferma/overwrite."""
from pathlib import Path

from app import writeback as W
from app.config import settings


def test_folder_for_scope():
    assert W.folder_for_scope("forma-core") == "forma"
    assert W.folder_for_scope("andrea") == "andrea-aloia"
    assert W.folder_for_scope("ovyon") == "ovyon"
    assert W.folder_for_scope("ats") == "forma/clienti/ats"


def test_slugify_sicuro():
    assert W.slugify("Piano Q3 2026!") == "piano-q3-2026"
    assert W.slugify("../../etc/passwd") == "etc-passwd"      # niente traversal
    assert W.slugify("Àccènti èùò") == "accenti-euo"
    assert W.slugify("") == "nota"


def test_render_note_facet_e_path():
    r = W.render_note("ats", "Report Cliente", "Corpo della nota.", tags=["report"])
    assert r["path"] == "forma/clienti/ats/generati/report-cliente.md"
    assert r["slug"] == "report-cliente"
    assert "tags: [forma, report]" in r["content"]   # facet forma iniettato
    assert "# Report Cliente" in r["content"]
    assert "Corpo della nota." in r["content"]

    # scope ovyon → facet ovyon, cartella ovyon
    r2 = W.render_note("ovyon", "Nota OVYON", "x")
    assert r2["path"].startswith("ovyon/generati/")
    assert "tags: [ovyon]" in r2["content"]


def test_save_note_crea_e_non_sovrascrive(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "vault_path", str(tmp_path))

    res = W.save_note("ats", "Report X", "Contenuto.", summary="prova")
    assert res["created"] is True
    dest = tmp_path / "forma/clienti/ats/generati/report-x.md"
    assert dest.exists()
    assert "Contenuto." in dest.read_text("utf-8")

    # seconda scrittura senza overwrite: non tocca il file
    res2 = W.save_note("ats", "Report X", "ALTRO.")
    assert res2["created"] is False
    assert "ALTRO." not in dest.read_text("utf-8")

    # con overwrite: aggiorna
    res3 = W.save_note("ats", "Report X", "AGGIORNATO.", overwrite=True)
    assert res3["created"] is True
    assert "AGGIORNATO." in dest.read_text("utf-8")
