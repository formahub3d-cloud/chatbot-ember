"""Una chiave pubblicata nel repo non autentica niente (05-08-2026).

Come è venuta fuori: cercando le chiavi del Postgres storico, tre delle quattro
erano `CHIAVE_FORMA_INTERNO`, `CHIAVE_ATS`, `CHIAVE_HRH` — le stringhe di
esempio di `tenants.example.json`, committate. La verifica su Railway ha poi
mostrato che le stesse tre erano in `TENANTS_JSON` e **autenticavano davvero**.

La peggiore è la prima: dà `forma-core` e **`andrea`** (le note personali) e non
ha `allowed_origins`, quindi vale da qualunque browser.

Questi test tengono chiusa quella porta. Girano offline.
"""
import json

import pytest

from app import security, tenants as T
from app.config import settings

SEGNAPOSTO = ("CHIAVE_FORMA_INTERNO", "CHIAVE_ATS", "CHIAVE_HRH")


@pytest.fixture(autouse=True)
def _pulisci(monkeypatch):
    """Sorgente statica con i tre segnaposto: è la situazione reale che il
    controllo deve rendere innocua."""
    monkeypatch.setattr(settings, "tenants_json", json.dumps({
        "CHIAVE_FORMA_INTERNO": {"name": "FORMA", "allowed_scopes": ["forma-core", "andrea"]},
        "CHIAVE_ATS": {"name": "ATS", "allowed_scopes": ["ats"]},
        "CHIAVE_HRH": {"name": "HRH", "allowed_scopes": ["hrh"]},
        "ember_chiave_vera_abc123": {"name": "Vera", "allowed_scopes": ["ats"]},
    }))
    monkeypatch.setattr(settings, "database_url", "")
    monkeypatch.setattr(settings, "chiavi_segnaposto_ammesse", False)
    monkeypatch.setattr(T, "_mongo_enabled", lambda: False)
    T._CACHE.update(data=None, ts=0.0)
    T._LEGACY.update(noto=False, valore=False)
    yield
    T._CACHE.update(data=None, ts=0.0)


@pytest.mark.parametrize("chiave", SEGNAPOSTO)
def test_il_segnaposto_non_autentica(chiave):
    """Anche se è nella sorgente dei tenant, non deve risolvere: 401."""
    assert T.get_tenant_by_key(chiave) is None


def test_una_chiave_vera_continua_a_funzionare():
    """Controprova: il controllo colpisce i tre valori noti, non tutti."""
    t = T.get_tenant_by_key("ember_chiave_vera_abc123")
    assert t is not None and t["allowed_scopes"] == ["ats"]


def test_il_riconoscimento_e_sull_hash_non_sulla_forma():
    """Non si cerca «CHIAVE_» nel testo: si confronta lo sha256. Una chiave vera
    che per caso cominciasse così non deve essere rifiutata."""
    assert security.e_segnaposto("CHIAVE_ATS") is True
    assert security.e_segnaposto("CHIAVE_ATS_2") is False
    assert security.e_segnaposto("chiave_ats") is False
    assert security.e_segnaposto("") is False


def test_la_finestra_di_grazia_e_esplicita(monkeypatch):
    """Durante la sostituzione dei valori serve poter riaprire per qualche
    minuto — ma è un interruttore che si vede, non un default."""
    monkeypatch.setattr(settings, "chiavi_segnaposto_ammesse", True)
    T._CACHE.update(data=None, ts=0.0)
    assert T.get_tenant_by_key("CHIAVE_ATS") is not None


def test_i_segnaposto_del_repo_sono_tutti_coperti():
    """Il registro non si scrive a mano due volte: se qualcuno aggiunge una
    chiave d'esempio a `tenants.example.json` senza metterla fra quelle
    rifiutate, questo test lo dice — altrimenti nasce una porta nuova con lo
    stesso difetto di quelle appena chiuse."""
    from pathlib import Path
    esempio = Path(__file__).resolve().parent.parent / "tenants.example.json"
    if not esempio.is_file():          # pragma: no cover — il file c'è
        pytest.skip("tenants.example.json assente")
    for chiave in json.loads(esempio.read_text("utf-8")):
        assert security.e_segnaposto(chiave), (
            f"«{chiave}» è pubblicata in tenants.example.json ma NON è fra le "
            "chiavi rifiutate: aggiungi il suo sha256 a security.CHIAVI_SEGNAPOSTO")
