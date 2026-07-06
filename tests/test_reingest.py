"""N2 · Script di re-ingest (scripts/reingest.py): costruzione richiesta + config."""
import importlib.util
import pathlib

_PATH = pathlib.Path(__file__).resolve().parent.parent / "scripts" / "reingest.py"
_spec = importlib.util.spec_from_file_location("reingest", _PATH)
reingest = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(reingest)


def test_build_request_url_e_header():
    req = reingest.build_request("https://ember.formahub.it/", "TOK")
    assert req.full_url == "https://ember.formahub.it/ingest"
    assert req.get_header("Authorization") == "Bearer TOK"
    assert req.method == "POST"


def test_build_request_normalizza_slash():
    req = reingest.build_request("https://ember.formahub.it", "X")
    assert req.full_url.endswith("/ingest") and "//ingest" not in req.full_url


def test_main_senza_token_esce_2(monkeypatch):
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    assert reingest.main() == 2
