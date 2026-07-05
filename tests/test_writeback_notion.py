"""Test del write-back Notion (Fase 2b): mappatura campi e chiamata API.

Puro, senza rete: httpx.post è mockato. Verifica la logica di conversione date
e tipologia, lo stato 'skipped' quando la config manca, e il payload inviato.
"""
from unittest.mock import MagicMock

from app import writeback as W
from app.config import settings


def test_to_iso_formati():
    assert W._to_iso("01/03/2026") == "2026-03-01"
    assert W._to_iso("01-03-2026") == "2026-03-01"
    assert W._to_iso("2026-03-01") == "2026-03-01"
    assert W._to_iso("非data") == ""
    assert W._to_iso("") == ""


def test_map_tipo():
    assert W._map_tipo("Tempo Determinato") == "Determinato"
    assert W._map_tipo("contratto indeterminato") == "Indeterminato"
    assert W._map_tipo("qualcosa di strano") == "Altro"
    assert W._map_tipo("") == "Altro"


def test_notion_skipped_senza_config(monkeypatch):
    monkeypatch.setattr(settings, "notion_token", "")
    monkeypatch.setattr(settings, "notion_contracts_db", "")
    res = W.notion_upsert({"nome": "Mario", "cognome": "Rossi"})
    assert res["status"] == "skipped"


def test_notion_upsert_payload(monkeypatch):
    monkeypatch.setattr(settings, "notion_token", "secret")
    monkeypatch.setattr(settings, "notion_contracts_db", "db-123")

    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"id": "page-abc"}
        return resp

    monkeypatch.setattr(W.httpx, "post", fake_post)

    res = W.notion_upsert({
        "nome": "Mario", "cognome": "Rossi",
        "codice_fiscale": "RSSMRA85M01H501Z",
        "codice_comunicazione": "12345",
        "data_inizio": "01/03/2026", "data_fine": "31/12/2026",
        "tipologia": "tempo determinato", "slug": "unilav-rossi-01-03-2026",
    })

    assert res["status"] == "ok"
    assert res["page_id"] == "page-abc"
    # auth + versione API
    assert captured["headers"]["Authorization"] == "Bearer secret"
    assert captured["headers"]["Notion-Version"] == W.NOTION_VERSION
    props = captured["json"]["properties"]
    assert captured["json"]["parent"]["database_id"] == "db-123"
    assert props["Nome e Cognome"]["title"][0]["text"]["content"] == "Mario Rossi"
    assert props["Tipo contratto"]["select"]["name"] == "Determinato"
    assert props["Data inizio"]["date"]["start"] == "2026-03-01"
    assert props["Data scadenza"]["date"]["start"] == "2026-12-31"
    assert props["Nota Obsidian"]["rich_text"][0]["text"]["content"] == "unilav-rossi-01-03-2026"


def test_notion_upsert_errore_http(monkeypatch):
    monkeypatch.setattr(settings, "notion_token", "secret")
    monkeypatch.setattr(settings, "notion_contracts_db", "db-123")

    def fake_post(url, headers=None, json=None, timeout=None):
        resp = MagicMock()
        resp.status_code = 400
        resp.text = "bad request"
        return resp

    monkeypatch.setattr(W.httpx, "post", fake_post)
    res = W.notion_upsert({"nome": "A", "cognome": "B"})
    assert res["status"] == "error"
    assert res["code"] == 400


def test_contract_note_related_per_cliente(tmp_path, monkeypatch):
    """La nota contratto usa i link related del cliente giusto (non piu' hard-coded ats)."""
    monkeypatch.setattr(settings, "vault_path", str(tmp_path))
    rel = W.save_contract_note({"nome": "Anna", "cognome": "Bianchi",
                                "data_inizio": "01/03/2026"}, cliente="hrh")
    content = (tmp_path / rel).read_text("utf-8")
    assert "[[registro-contratti-hrh]]" in content
    assert "[[cliente-hrh]]" in content
    assert "registro-contratti-ats" not in content
