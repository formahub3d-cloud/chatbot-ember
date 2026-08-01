"""«Human · evoluzione» (01-08): dati sanitari = categoria speciale GDPR.

La decisione di design, provata qui:
  1. `human/` è FUORI dal perimetro dell'ingest — nessun frammento in Qdrant,
     nessun retrieval può restituirlo, Divina non ci risponde PER COSTRUZIONE;
  2. il pannello legge dal DISCO del vault via /admin/human, solo owner
     (ADMIN_TOKEN), mai chiavi tenant;
  3. la nota assente si dice assente — mai un errore nudo.
"""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import main
from app.config import settings
from app.ingest import is_note_included

TOK = "tok-di-test-lungo-abbastanza-123456"


def test_human_e_fuori_dal_perimetro_ingest():
    assert is_note_included(Path("andrea-aloia/self-andrea-aloia.md")) is True
    assert is_note_included(Path("andrea-aloia/human/human-evoluzione.md")) is False
    assert is_note_included(Path("andrea-aloia/human/salute-2026.md")) is False
    # come contratti/: l'esclusione vale ovunque nel path
    assert is_note_included(Path("forma/clienti/ats/contratti/x.md")) is False


@pytest.fixture()
def cl(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "admin_token", TOK)
    monkeypatch.setattr(settings, "vault_path", str(tmp_path))
    return TestClient(main.app)


def test_admin_human_richiede_owner(cl):
    assert cl.get("/admin/human").status_code == 401                     # niente token
    r = cl.get("/admin/human", headers={"X-Tenant-Key": "ovy_x"})        # chiave tenant ≠ owner
    assert r.status_code == 401


def test_admin_human_nota_assente_detta_assente(cl):
    r = cl.get("/admin/human", headers={"Authorization": f"Bearer {TOK}"})
    assert r.status_code == 200
    d = r.json()
    assert d["exists"] is False and "human-evoluzione" in d["path"]


def test_admin_human_legge_dal_disco(cl, tmp_path):
    p = tmp_path / "andrea-aloia" / "human"
    p.mkdir(parents=True)
    (p / "human-evoluzione.md").write_text(
        "# Human\n\n## Salute\n- peso: 78 kg (2026-08-01)\n", encoding="utf-8")
    r = cl.get("/admin/human", headers={"Authorization": f"Bearer {TOK}"})
    assert r.status_code == 200
    d = r.json()
    assert d["exists"] is True and "78 kg" in d["text"] and d["updated"]
