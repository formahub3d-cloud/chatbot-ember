"""V10/A · Il clone del vault è una dipendenza, come le tabelle.

Il difetto, visto due volte il 2/08 e la seconda con conseguenze. Su Railway
ogni redeploy fa un container nuovo e la cartella del vault non c'è:
`vault_info()` torna `{}`, l'allarme sui commit ha bisogno di due valori per
confrontarli e **si spegne da solo**. Alle 17:40 lo stato era:

    vault:          {}
    ingest_commit:  8ed778cbd45b   ← il commit del V8
    allarme:        spento
    quadro:         6,9            ← il punteggio vecchio, mostrato come nuovo

Il V9 era mergiato da venti minuti. Quel giorno le variabili di Railway sono
state toccate cinque volte: cinque redeploy, cinque volte l'allarme cieco.
"""
import pytest
from fastapi.testclient import TestClient

from app import dbcheck, degrado, ingest, main
from app.config import settings

TOK = "tok-di-test-lungo-abbastanza-123456"
AUTH = {"Authorization": f"Bearer {TOK}"}


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(settings, "admin_token", TOK)
    return TestClient(main.app)


@pytest.fixture(autouse=True)
def _db_a_posto(monkeypatch):
    """Un database completo: qui si misura il VAULT, non le tabelle."""
    monkeypatch.setattr(settings, "grants_backend", "supabase")
    monkeypatch.setattr(settings, "database_url", "postgres://x/y")
    tabelle = {t for t, _c, _d, _r in dbcheck.ATTESE}
    colonne = {(t, c) for t, c, _d, _r in dbcheck.ATTESE
               if c and not c.startswith("@check:")}
    check = {(t, "@check:CHECK (status = ANY (ARRAY['da-verificare'::text]))")
             for t, c, _d, _r in dbcheck.ATTESE if c and c.startswith("@check:")}
    monkeypatch.setattr(dbcheck, "_trovate", lambda: (tabelle, colonne | check))


def _vault(monkeypatch, url="https://github.com/x/vault.git", commit="8ed778cbd45b"):
    monkeypatch.setattr(settings, "vault_git_url", url)
    monkeypatch.setattr(ingest, "vault_info",
                        lambda *a, **k: {"vault_commit": commit,
                                         "vault_commit_date": "2026-08-02T12:00:00+00:00"}
                        if commit else {})


# ══════════════════════════════════════════════════════════════════════════
# A1 · Il clone entra nel registro, con gli stessi tre esiti delle tabelle
# ══════════════════════════════════════════════════════════════════════════
def test_col_clone_al_suo_posto_non_si_mostra_niente(monkeypatch):
    _vault(monkeypatch)
    assert degrado.per("allarme-commit")["stato"] == "acceso"


def test_il_container_nuovo_lo_dice_invece_di_spegnersi(monkeypatch):
    """IL caso delle 17:40. La frase non dice «manca il clone» — quello è il
    rimedio, e sta nella riga tecnica: dice che il confronto non si può fare."""
    _vault(monkeypatch, commit="")
    d = degrado.per("allarme-commit")
    assert d["stato"] == "spento"
    assert "on si può confrontare" in d["perche"]
    assert "dopo il riavvio" in d["perche"]
    assert d["manca"] == ["clone del vault"]
    assert d["dove"]


def test_senza_repo_del_vault_e_una_configurazione_non_un_guasto(monkeypatch):
    """In sviluppo si legge una cartella locale: non esiste un commit da
    confrontare, e dirlo come un guasto sarebbe un allarme inventato."""
    _vault(monkeypatch, url="", commit="")
    d = degrado.per("allarme-commit")
    assert d["stato"] == "spento" and d["manca"] == ["VAULT_GIT_URL"]
    assert "cartella locale" in d["perche"]


def test_un_accertamento_che_esplode_e_il_terzo_esito(monkeypatch):
    monkeypatch.setattr(settings, "vault_git_url", "https://x/y.git")
    monkeypatch.setattr(ingest, "vault_info",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("disco")))
    d = degrado.per("allarme-commit")
    assert d["stato"] == "non-so" and d["manca"] == []


def test_il_clone_e_la_tabella_si_sommano_in_una_frase_sola(monkeypatch):
    """L'allarme dipende da due cose di natura diversa — una cartella e una
    tabella — e chi guarda non deve leggere due avvisi per capire una cosa."""
    _vault(monkeypatch, commit="")
    monkeypatch.setattr(dbcheck, "_trovate",
                        lambda: ({t for t, _c, _d, _r in dbcheck.ATTESE if t != "ingest_meta"},
                                 set()))
    d = degrado.per("allarme-commit")
    assert d["stato"] == "spento"
    assert "clone del vault" in d["manca"] and "ingest_meta" in d["manca"]
    assert d["perche"].count(".") <= 1          # una frase, non un elenco puntato


def test_l_allarme_viaggia_con_la_pagina_del_cervello(client, monkeypatch):
    """La regola 6: non basta che `/admin/status` lo sappia."""
    _vault(monkeypatch, commit="")
    monkeypatch.setattr(main.brain, "enabled", lambda: False)
    monkeypatch.setattr(main.brain, "stats", lambda: {})
    monkeypatch.setattr(main.brain, "notes", lambda **k: [])
    monkeypatch.setattr(main.brain, "ingest_commit", lambda: {"vault_commit": "8ed778cbd45b"})
    d = client.get("/admin/brain", headers=AUTH).json()
    assert d["vault"] == {} and d["degrado"]["stato"] == "spento"
    assert "on si può confrontare" in d["degrado"]["perche"]


# ══════════════════════════════════════════════════════════════════════════
# A2 · Il clone si riprende da solo — e NON si reindicizza
# ══════════════════════════════════════════════════════════════════════════
def test_al_primo_avvio_senza_clone_lo_prende(monkeypatch):
    chiamate = []
    monkeypatch.setattr(settings, "vault_boot_clone", True)
    monkeypatch.setattr(settings, "vault_path", "/tmp/vault")
    monkeypatch.setattr(settings, "vault_git_url", "https://x/y.git")
    stato = {"clone": False}
    monkeypatch.setattr(ingest, "vault_info",
                        lambda *a, **k: {"vault_commit": "abc123456789"} if stato["clone"] else {})

    def finto_sync(*a, **k):
        chiamate.append(a)
        stato["clone"] = True
        return True
    monkeypatch.setattr(ingest, "sync_vault", finto_sync)
    r = ingest.procura_clone()
    assert r["fatto"] is True and r["vault_commit"] == "abc123456789"
    assert len(chiamate) == 1


def test_non_reindicizza_mai(monkeypatch):
    """La scelta del blocco, e il test che la tiene ferma. Qdrant sta fuori dal
    container e sopravvive al redeploy: reindicizzare all'avvio ricalcolerebbe
    gli embedding di ogni nota per riscrivere lo stesso indice — e su Railway,
    che riavvia anche senza deploy, un ciclo di riavvii diventerebbe un ciclo di
    reindicizzazioni contro l'API degli embedding."""
    monkeypatch.setattr(settings, "vault_boot_clone", True)
    monkeypatch.setattr(settings, "vault_path", "/tmp/vault")
    monkeypatch.setattr(settings, "vault_git_url", "https://x/y.git")
    monkeypatch.setattr(ingest, "vault_info", lambda *a, **k: {})
    monkeypatch.setattr(ingest, "sync_vault", lambda *a, **k: True)
    monkeypatch.setattr(ingest, "run",
                        lambda: pytest.fail("l'avvio NON deve reindicizzare"))
    ingest.procura_clone()


def test_se_il_clone_c_e_gia_non_tocca_niente(monkeypatch):
    monkeypatch.setattr(settings, "vault_boot_clone", True)
    monkeypatch.setattr(settings, "vault_path", "/tmp/vault")
    monkeypatch.setattr(settings, "vault_git_url", "https://x/y.git")
    monkeypatch.setattr(ingest, "vault_info", lambda *a, **k: {"vault_commit": "gia"})
    monkeypatch.setattr(ingest, "sync_vault",
                        lambda *a, **k: pytest.fail("clone già presente: niente git"))
    assert ingest.procura_clone()["fatto"] is False


def test_un_clone_fallito_non_si_racconta_come_riuscito(monkeypatch):
    """Il motore parte lo stesso — un guardrail che impedisce l'avvio sarebbe
    peggio del guasto — ma `fatto` resta False e il degrado lo dichiara,
    perché guarda il RISULTATO e non il tentativo."""
    monkeypatch.setattr(settings, "vault_boot_clone", True)
    monkeypatch.setattr(settings, "vault_path", "/tmp/vault")
    monkeypatch.setattr(settings, "vault_git_url", "https://x/y.git")
    monkeypatch.setattr(ingest, "vault_info", lambda *a, **k: {})
    monkeypatch.setattr(ingest, "sync_vault",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("rete")))
    r = ingest.procura_clone()
    assert r["fatto"] is False and "RuntimeError" in r["motivo"]
    assert degrado.per("allarme-commit")["stato"] == "spento"


def test_si_puo_spegnere(monkeypatch):
    monkeypatch.setattr(settings, "vault_boot_clone", False)
    monkeypatch.setattr(settings, "vault_git_url", "https://x/y.git")
    monkeypatch.setattr(ingest, "sync_vault",
                        lambda *a, **k: pytest.fail("spento: non deve clonare"))
    assert ingest.procura_clone()["fatto"] is False


def test_non_clona_mentre_una_ingest_sta_gia_clonando(monkeypatch):
    """`_fresh_clone_swap` rinomina la cartella: due git in parallelo sulla
    stessa directory sono il modo più veloce di ritrovarsi con mezzo vault."""
    monkeypatch.setattr(settings, "vault_boot_clone", True)
    monkeypatch.setattr(settings, "vault_path", "/tmp/vault")
    monkeypatch.setattr(settings, "vault_git_url", "https://x/y.git")
    monkeypatch.setattr(ingest, "vault_info", lambda *a, **k: {})
    monkeypatch.setattr(ingest, "sync_vault",
                        lambda *a, **k: pytest.fail("lock preso: non deve clonare"))
    import threading
    partito, libera = threading.Event(), threading.Event()

    def occupa():
        with ingest._GIT:
            partito.set()
            libera.wait(5)
    t = threading.Thread(target=occupa, daemon=True)
    t.start()
    partito.wait(5)
    try:
        r = ingest.procura_clone()
        assert r["fatto"] is False and "già in corso" in r["motivo"]
    finally:
        libera.set()
        t.join(5)
