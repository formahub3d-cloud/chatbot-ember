"""S5.1b (motore) · Il registro dalla parte della chat, e la guardia sul ruolo.

La chat è il consumo grosso: senza questa metà il registro conterebbe metà del
traffico, e il fail-closed guarderebbe un numero sbagliato.

Le due cose che questi test tengono ferme, e sono la ragione per cui il modulo
esiste in questa forma:

  · **senza `DATABASE_URL_LEDGER` il registro è spento e lo DICE.** Non ripiega
    sulla connessione privilegiata del motore: quella scavalcherebbe
    append-only e RLS, e la stessa tabella avrebbe due regole a seconda di chi
    scrive. Un consumo non registrato è un problema di fatturazione; un consumo
    registrato scavalcando le difese è un problema di fiducia nei dati;
  · **la contabilità non fa fallire la risposta.** A quel punto l'utente l'ha
    già letta: un'eccezione qui trasformerebbe una riga mancante in una
    risposta che sembra andata storta.
"""
import pytest

from app import ledger, tariffa, uso
from app.config import settings

# La forma VERA di un tenant nel motore: una CHIAVE con scope e branding.
# Non ha `tenant_id`/`org_code`/`code` — quella è la forma dell'orchestratore, e
# confonderle è il difetto del 6/08 (tenant=None nei log di produzione).
TENANT = {"name": "ATS", "allowed_scopes": ["ats"], "allowed_origins": [],
          "branding": {"tenant_code": "ats"}, "quota_day": 0}

SENZA_CODICE = {"name": "dogfood FORMA", "allowed_scopes": ["forma-core", "andrea"],
                "branding": {}, "quota_day": 0}


class _Cur:
    """Cursore finto: registra e risponde ai due SELECT che il modulo fa."""

    def __init__(self, saldi=(("mensile", 1_000_000),),
                 anagrafica=("uuid-ats", "forma")):
        self.saldi = list(saldi)
        self.anagrafica = anagrafica
        self.eseguiti = []

    def execute(self, sql, params=None):
        self.eseguiti.append((" ".join(sql.split()), params))

    def fetchall(self):
        return self.saldi

    def fetchone(self):
        # l'anagrafica: (tenant_id, org_code) dalla tabella `tenants`
        return self.anagrafica

    def inserimenti(self):
        return [(s, p) for s, p in self.eseguiti if s.startswith("INSERT INTO token_ledger")]


@pytest.fixture
def sessione_finta(monkeypatch):
    """Sostituisce la connessione: i test non aprono niente."""
    from contextlib import contextmanager
    cur = _Cur()

    @contextmanager
    def _finta(tenant):
        yield cur

    monkeypatch.setattr(settings, "database_url_ledger", "postgresql://divina@finta/db")
    monkeypatch.setattr(ledger, "_sessione", _finta)
    monkeypatch.setattr(ledger, "_senza_misura", False)
    monkeypatch.setattr(ledger, "_spento_detto", False)
    monkeypatch.setattr(ledger, "_senza_tenant_detto", set())
    return cur


# ── la guardia sul ruolo ─────────────────────────────────────────────────────

def test_senza_la_variabile_il_registro_e_SPENTO_e_non_ripiega(monkeypatch, caplog):
    """Il ripiego silenzioso sulla connessione privilegiata è il difetto per cui
    questa variabile esiste."""
    aperture = []
    monkeypatch.setattr(settings, "database_url_ledger", "")
    monkeypatch.setattr(settings, "database_url", "postgresql://postgres@vero/db")
    monkeypatch.setattr(ledger, "_sessione",
                        lambda t: aperture.append(t) or (_ for _ in ()).throw(
                            AssertionError("non deve aprire nessuna connessione")))
    monkeypatch.setattr(ledger, "_spento_detto", False)

    esito = ledger.addebita(TENANT, "chat", uso.Uso(10, 5))
    assert esito == {"scritto": False, "motivo": "spento", "token": 0}
    assert aperture == []
    assert ledger.attivo() is False


def test_con_la_variabile_il_registro_e_attivo(monkeypatch):
    monkeypatch.setattr(settings, "database_url_ledger", "postgresql://divina@x/db")
    assert ledger.attivo() is True


def test_lo_spento_si_dice_UNA_volta_sola(monkeypatch, caplog):
    """Un errore per messaggio trasformerebbe il log in rumore, e il rumore è
    dove le cose importanti si perdono."""
    import logging
    monkeypatch.setattr(settings, "database_url_ledger", "")
    monkeypatch.setattr(ledger, "_spento_detto", False)
    with caplog.at_level(logging.ERROR):
        for _ in range(5):
            ledger.addebita(TENANT, "chat", uso.Uso(1, 1))
    assert sum("registro token SPENTO" in r.message for r in caplog.records) == 1


# ── la scrittura ─────────────────────────────────────────────────────────────

def test_una_chat_misurata_scrive_la_riga(sessione_finta):
    esito = ledger.addebita(TENANT, "chat", uso.Uso(100, 50))
    assert esito["scritto"] is True
    assert esito["token"] == 150 and esito["misura"] == "misurato"
    sql, params = sessione_finta.inserimenti()[0]
    assert params[3] == "addebito" and params[4] == "mensile"
    assert params[9] == 150


def test_il_moltiplicatore_arriva_dal_LISTINO_non_dal_chiamante(sessione_finta):
    """Il prezzo non lo decide chi consuma: se lo passasse il chiamante, due
    percorsi diversi potrebbero prezzare la stessa operazione in modo diverso."""
    ledger.addebita(TENANT, "documento", uso.Uso(100, 0))
    _, params = sessione_finta.inserimenti()[0]
    assert params[6] == tariffa.moltiplicatore("documento") == 4
    assert params[9] == 400


def test_la_voce_e_inclusa_e_la_riga_si_scrive_lo_stesso(sessione_finta):
    esito = ledger.addebita(TENANT, "voce", uso.Uso(500, 200))
    assert esito["token"] == 0
    assert len(sessione_finta.inserimenti()) == 1, "«gratis» è un'informazione"


def test_un_consumo_non_misurato_lascia_la_riga_ignoto(sessione_finta):
    esito = ledger.addebita(TENANT, "chat", None)
    assert esito["misura"] == "ignoto" and esito["token"] == 0
    _, params = sessione_finta.inserimenti()[0]
    assert params[-1] == "ignoto"


def test_a_cavallo_di_due_borselli_due_righe(monkeypatch, sessione_finta):
    sessione_finta.saldi = [("mensile", 40), ("extra", 500)]
    esito = ledger.addebita(TENANT, "chat", uso.Uso(100, 0))
    assert esito["righe"] == [("mensile", 40), ("extra", 60)]
    assert [p[4] for _, p in sessione_finta.inserimenti()] == ["mensile", "extra"]


def test_i_GUC_del_tenant_si_impostano_anche_in_SCRITTURA(monkeypatch):
    """La policy RLS ha un `with check`: senza i GUC l'INSERT viene rifiutato
    dal database — il che è la prova che l'isolamento c'è, ma va fatto bene."""
    visti = {}

    class _Conn:
        def cursor(self):
            return _Cur()

        def commit(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(settings, "database_url_ledger", "postgresql://divina@x/db")
    monkeypatch.setattr(ledger.rls, "set_grants",
                        lambda cur, grants: visti.update(grants=grants))
    import sys, types
    finto = types.ModuleType("psycopg2")
    finto.connect = lambda *a, **k: _Conn()
    monkeypatch.setitem(sys.modules, "psycopg2", finto)

    with ledger._sessione(TENANT):
        pass
    assert visti["grants"] == ["ats"]


# ── la contabilità non rompe la risposta ─────────────────────────────────────

def test_un_errore_di_scrittura_NON_solleva(monkeypatch):
    """La risposta l'utente l'ha già letta: un'eccezione qui la farebbe sembrare
    andata storta."""
    from contextlib import contextmanager

    @contextmanager
    def _rotta(tenant):
        raise RuntimeError("pooler giù")
        yield  # pragma: no cover

    monkeypatch.setattr(settings, "database_url_ledger", "postgresql://divina@x/db")
    monkeypatch.setattr(ledger, "_sessione", _rotta)

    esito = ledger.addebita(TENANT, "chat", uso.Uso(10, 5))
    assert esito == {"scritto": False, "motivo": "errore", "token": 15}


def test_un_operazione_ignota_non_solleva_ma_lo_dice(sessione_finta):
    esito = ledger.addebita(TENANT, "inventata", uso.Uso(1, 1))
    assert esito["scritto"] is False and esito["motivo"] == "operazione-ignota"
    assert sessione_finta.inserimenti() == []


# ── le due copie non devono divergere ────────────────────────────────────────

def test_la_ripartizione_e_IDENTICA_a_quella_dell_orchestratore():
    """Se un giorno divergessero, lo stesso cliente pagherebbe in due modi
    diversi a seconda di quale servizio ha risposto."""
    casi = [
        (100, {"mensile": 500}),
        (100, {"mensile": 30, "extra": 900}),
        (60, {"mensile": 10, "extra": 20, "regalo": 100}),
        (100, {"mensile": 10, "extra": 5}),
        (0, {"mensile": 100}),
    ]
    attesi = [
        [("mensile", 100)],
        [("mensile", 30), ("extra", 70)],
        [("mensile", 10), ("extra", 20), ("regalo", 30)],
        [("mensile", 10), ("extra", 5)],
        [],
    ]
    for (quanti, saldi), atteso in zip(casi, attesi):
        assert ledger.ripartisci(quanti, saldi) == atteso


def test_l_ordine_dei_borselli_e_lo_stesso():
    assert ledger.BORSELLI == ("mensile", "extra", "regalo")


def test_il_listino_copre_le_operazioni_del_registro():
    assert set(tariffa.CONSUMI) | set(tariffa.ACCREDITI) == set(ledger.OPERAZIONI)


# ── l'identità del tenant: il difetto del 6/08 ───────────────────────────────

def test_il_codice_si_legge_dal_BRANDING_non_dagli_scope():
    """La stessa parola per due cose diverse. Di là un tenant è una riga di
    `tenants`; di qua è una chiave API con dentro gli scope."""
    assert ledger.codice_tenant(TENANT) == "ats"
    assert ledger.codice_tenant(SENZA_CODICE) == ""
    assert ledger.codice_tenant({}) == ""


def test_una_chiave_SENZA_tenant_code_non_prova_nemmeno_a_scrivere(sessione_finta, caplog):
    """È il caso della chiave dogfood: due scope, nessun codice.

    Prima si provava e si falliva dentro, con un errore generico che non diceva
    che il problema era l'identità mancante. Adesso si dichiara PRIMA.
    """
    import logging
    with caplog.at_level(logging.ERROR):
        esito = ledger.addebita(SENZA_CODICE, "chat", uso.Uso(1000, 500))

    assert esito == {"scritto": False, "motivo": "senza-tenant", "token": 0}
    assert sessione_finta.inserimenti() == []
    detto = " ".join(r.getMessage() for r in caplog.records)
    assert "tenant_code" in detto and "forma-core" in detto


def test_gli_scope_NON_diventano_un_tenant(sessione_finta):
    """Una chiave può avere più scope: sceglierne uno vorrebbe dire attribuire
    il consumo a caso. Meglio non scrivere che scrivere sul cliente sbagliato."""
    ledger.addebita(SENZA_CODICE, "chat", uso.Uso(10, 5))
    scritti = [p[2] for _, p in sessione_finta.inserimenti()]
    assert "forma-core" not in scritti and "andrea" not in scritti


def test_un_codice_che_l_anagrafica_non_conosce_non_si_scrive(sessione_finta):
    """`tenant_id` e `org_code` sono NOT NULL con una FK: un codice che il
    database non conosce è un dato sbagliato, non una riga da scrivere lo
    stesso."""
    sessione_finta.anagrafica = None
    esito = ledger.addebita(TENANT, "chat", uso.Uso(10, 5))
    assert esito["scritto"] is False and esito["motivo"] == "tenant-sconosciuto"
    assert sessione_finta.inserimenti() == []


def test_l_anagrafica_riempie_tenant_id_e_org_code(sessione_finta):
    ledger.addebita(TENANT, "chat", uso.Uso(10, 5))
    _, params = sessione_finta.inserimenti()[0]
    assert params[0] == "uuid-ats"      # tenant_id dall'anagrafica
    assert params[1] == "forma"         # org_code dall'anagrafica
    assert params[2] == "ats"           # tenant_code dal branding


def test_l_anagrafica_fa_la_JOIN_con_organizations(sessione_finta):
    """`tenants` ha `org_id`, non `org_code`: il codice testuale sta in
    `organizations.code`. Senza la JOIN è un `UndefinedColumn` in produzione, ed
    è successo il 7/08 — perché il test guardava il RISULTATO del finto invece
    della FORMA della query. Un cursore finto risponde a qualunque SQL, anche a
    uno che il database rifiuterebbe: qui si guarda la query."""
    ledger.addebita(TENANT, "chat", uso.Uso(10, 5))
    letture = [s for s, _ in sessione_finta.eseguiti if "FROM tenants" in s]
    assert letture, "l'anagrafica non è stata chiesta"
    assert "JOIN organizations" in letture[0]
    assert "o.org_id = t.org_id" in letture[0]
    assert "org_code FROM tenants" not in letture[0]
