"""S5.1c · Lo script del rapporto, ESEGUITO.

Nasce da un difetto mio del 7/08, trovato da Kimi lanciandolo in produzione:

    cur.execute("SELECT set_config(%s, %s, true)", (nome, valore, True))
                                   └── due ─┘        └──── tre ────┘

    TypeError: not all arguments converted during string formatting

Lo script non partiva proprio. Io avevo verificato che l'SQL fosse
sintatticamente valido (`ast.parse`) e l'avevo lanciato senza
`DATABASE_URL_LEDGER` — cioè su un percorso che esce prima di toccare il
database. **Ho controllato la forma, non il comportamento**, su una correzione
che serviva esattamente a far vedere il comportamento.

Il cursore finto qui sotto conta i segnaposto e li confronta coi parametri: è
la sola cosa che quel difetto non avrebbe potuto attraversare.
"""
import importlib.util
import pathlib

import pytest

_SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "rapporto_misura.py"


def _modulo():
    spec = importlib.util.spec_from_file_location("rapporto_misura", _SCRIPT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class _CursorePignolo:
    """Un cursore che rifiuta quello che psycopg2 rifiuterebbe.

    `psycopg2` solleva `TypeError: not all arguments converted` quando i
    parametri sono più dei segnaposto — e siccome nei test il cursore è sempre
    finto, quell'errore non lo vede nessuno finché non lo vede un utente.
    """

    def __init__(self):
        self.eseguite = []

    def execute(self, sql, params=None):
        segnaposto = sql.count("%s")
        quanti = len(params) if params is not None else 0
        if segnaposto != quanti:
            raise TypeError(
                f"segnaposto {segnaposto} ≠ parametri {quanti}: {sql!r}")
        self.eseguite.append((sql, params))


def test_i_guc_si_impostano_senza_esplodere():
    """Il test che sarebbe bastato: lo esegue invece di leggerlo."""
    cur = _CursorePignolo()
    _modulo().imposta_guc(cur, "forma-core")
    assert len(cur.eseguite) == 3


def test_il_tenant_va_nel_guc_dei_TENANT_e_in_nessun_altro():
    """`allowed_sub_tenants` finisce anch'esso per «tenants»: una condizione
    scritta come `nome.endswith("tenants")` ci metterebbe dentro un codice di
    un altro livello. Sembra furba e sbaglia."""
    valori = dict(_modulo().guc_per("forma-core"))
    assert valori["ovyon.allowed_tenants"] == "forma-core"
    assert valori["ovyon.allowed_orgs"] == ""
    assert valori["ovyon.allowed_sub_tenants"] == ""


def test_la_vista_completa_passa_dal_carattere_che_la_RLS_riconosce():
    """`'*'` in `allowed_tenants` accende `ovyon.is_master()` (db/schema.sql):
    è il modo documentato di guardare tutti i tenant, non una convenzione
    nostra."""
    assert dict(_modulo().guc_per("*"))["ovyon.allowed_tenants"] == "*"


def test_senza_tenant_lo_script_si_ferma_e_dice_perche(monkeypatch, capsys):
    """Un default silenzioso qui vuol dire un rapporto che sembra vuoto invece
    di uno che chiede una cosa."""
    m = _modulo()
    monkeypatch.setenv("DATABASE_URL_LEDGER", "postgresql://finta")
    monkeypatch.setattr(m.sys, "argv", ["rapporto_misura.py"])
    assert m.main() == 2
    assert "--tenant" in capsys.readouterr().err


def test_senza_stringa_di_connessione_si_ferma_prima(monkeypatch, capsys):
    m = _modulo()
    monkeypatch.delenv("DATABASE_URL_LEDGER", raising=False)
    monkeypatch.setattr(m.sys, "argv", ["rapporto_misura.py", "--tenant", "*"])
    assert m.main() == 2
    assert "DATABASE_URL_LEDGER" in capsys.readouterr().err


def test_la_riga_dei_guc_e_la_STESSA_di_quella_in_produzione():
    """`app/rls.set_grants` gira a ogni chat; questa gira una volta ogni tanto,
    a mano. Due copie della stessa riga devono essere identiche, non
    somigliarsi — e la differenza fra le due era proprio il segnaposto
    mancante."""
    from app import rls

    class _Spia:
        def __init__(self):
            self.sql = []

        def execute(self, sql, params=None):
            self.sql.append((sql, len(params or ())))

    vera, script = _Spia(), _Spia()
    rls.set_grants(vera, ["forma-core"])
    _modulo().imposta_guc(script, "forma-core")
    assert {s for s, _ in vera.sql} == {s for s, _ in script.sql}
    assert {n for _, n in vera.sql} == {n for _, n in script.sql}
