"""S1.1 · La sorgente dei tenant si sceglie guardando, non sbagliando.

Il Postgres allegato al servizio su Railway è un fossile: dentro c'è una sola
tabella, `tenants`, con la forma storica `key/name/allowed_scopes` — creata da
`ensure_seeded()` quando quel database ERA il tenant store. Oggi DATABASE_URL
punta a Supabase, dove `tenants` è la tabella dello schema OVYON e la colonna
`key` non esiste.

Prima di questo cambiamento `get_tenants()` provava lo stesso la query storica a
ogni scadenza di cache, prendeva l'eccezione e ripiegava sulla sorgente statica:
il risultato era giusto, la strada no — uno stack trace ogni 60 secondi e un
comportamento che dipendeva da un errore. E `ensure_seeded()` creava la tabella
storica su qualunque database trovasse: su un Supabase vuoto avrebbe occupato il
nome `tenants` con lo schema sbagliato, e l'orchestratore avrebbe risposto
«tenant sconosciuto» per sempre.

Connessione finta, nessuna rete.
"""
import json

from app import tenants as T
from app.config import settings


class _Cur:
    """Cursore finto: dice se la colonna `key` esiste e registra il DDL visto."""

    def __init__(self, ha_colonna_key: bool, eseguiti: list):
        self.ha_colonna_key = ha_colonna_key
        self.eseguiti = eseguiti
        self._row = None
        self._rows = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=()):
        self.eseguiti.append(" ".join(sql.split()))
        s = sql.upper()
        if "INFORMATION_SCHEMA.COLUMNS" in s:
            self._row = (1,) if self.ha_colonna_key else None
        elif "COUNT(*)" in s:
            self._row = (1,)                      # tabella già popolata
        elif "SELECT KEY, NAME, ALLOWED_SCOPES" in s:
            self._rows = [("chiave-ats", "ATS", json.dumps(["ats"]))]

    def fetchone(self):
        return self._row

    def fetchall(self):
        return self._rows


class _Conn:
    def __init__(self, ha_colonna_key, eseguiti):
        self.ha_colonna_key = ha_colonna_key
        self.eseguiti = eseguiti

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def cursor(self):
        return _Cur(self.ha_colonna_key, self.eseguiti)

    def commit(self):
        pass


def _prepara(monkeypatch, ha_colonna_key: bool):
    eseguiti: list = []
    monkeypatch.setattr(T, "_conn", lambda: _Conn(ha_colonna_key, eseguiti))
    monkeypatch.setattr(T, "_mongo_enabled", lambda: False)
    monkeypatch.setattr(settings, "database_url", "postgresql://finto/db")
    monkeypatch.setattr(settings, "tenants_json",
                        json.dumps({"chiave-statica": {"name": "Statico",
                                                       "allowed_scopes": ["forma-core"]}}))
    T._LEGACY.update(noto=False, valore=False)
    T._CACHE.update(data=None, ts=0.0)
    return eseguiti


def test_tabella_ovyon_sorgente_statica_e_zero_query_storiche(monkeypatch):
    """Forma OVYON (niente colonna `key`): si usa TENANTS_JSON e la query
    storica non parte nemmeno. È la differenza fra scegliere e sbagliare."""
    eseguiti = _prepara(monkeypatch, ha_colonna_key=False)

    dati = T.get_tenants()

    assert dati == {"chiave-statica": {"name": "Statico", "allowed_scopes": ["forma-core"]}}
    assert not any("SELECT key, name, allowed_scopes" in e for e in eseguiti), \
        "la query storica non deve partire su una tabella che non ha quella forma"


def test_tabella_storica_ancora_sorgente_del_db(monkeypatch):
    """Controprova: dove la forma storica c'è davvero, il comportamento non
    cambia di una virgola — questo lavoro toglie un errore, non una funzione."""
    _prepara(monkeypatch, ha_colonna_key=True)

    dati = T.get_tenants()

    assert dati == {"chiave-ats": {"name": "ATS", "allowed_scopes": ["ats"]}}


def test_ensure_seeded_non_crea_piu_la_tabella_storica(monkeypatch):
    """Il guasto peggiore era il più silenzioso: `CREATE TABLE tenants(key…)`
    su un database vuoto rende l'orchestratore cieco senza dire perché."""
    eseguiti = _prepara(monkeypatch, ha_colonna_key=False)

    T.ensure_seeded()

    assert not any("CREATE TABLE" in e.upper() for e in eseguiti)


def test_forma_non_verificabile_non_e_un_si(monkeypatch):
    """Se la domanda sulla forma non riceve risposta (DB irraggiungibile), non
    si conclude che la tabella storica c'è: si ripiega e si riproverà."""
    def _esplode():
        raise RuntimeError("pooler giù")

    monkeypatch.setattr(T, "_conn", _esplode)
    monkeypatch.setattr(T, "_mongo_enabled", lambda: False)
    monkeypatch.setattr(settings, "database_url", "postgresql://finto/db")
    T._LEGACY.update(noto=False, valore=False)

    assert T.tenants_legacy() is False
    assert T._LEGACY["noto"] is False, "un non-so non si mette in cache come un no"
