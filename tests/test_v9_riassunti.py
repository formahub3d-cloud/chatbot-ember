"""V9/D · La conversazione che dura (audit-2026-08-02-48, audit-2026-08-02-49).

Il pezzo che tiene insieme il tono, il muro-che-diventa-porta, il filo e la
memoria delle preferenze: una conversazione che si può riprendere il giorno dopo.

I due limiti sono il vero contenuto di questo file. Il riassunto non allarga i
permessi — uno scope toccato ieri non dà diritti oggi — e il riassunto È un dato
personale: retention applicata, e raggiungibile dal «Dimentica». Se il bottone
non ci arriva, l'articolo 17 è coperto a metà.
"""
import time

import pytest
from fastapi.testclient import TestClient

from app import filo, main, memoria, riassunti
from app.config import settings

TOK = "tok-di-test-lungo-abbastanza-123456"
AUTH = {"Authorization": f"Bearer {TOK}"}

TURNI = [
    {"role": "user", "content": "dobbiamo preparare il materiale per ATS"},
    {"role": "assistant", "content": "Va bene. Da dove partiamo?"},
    {"role": "user", "content": "dalla scheda cliente, che è vuota"},
    {"role": "assistant", "content": "La riscriviamo partendo dal loro sito."},
]


@pytest.fixture(autouse=True)
def _pulizia():
    riassunti.reset()
    memoria.reset()
    filo.dimentica()
    yield
    riassunti.reset()
    memoria.reset()
    filo.dimentica()


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(settings, "admin_token", TOK)
    return TestClient(main.app)


def _modello(monkeypatch, testo="Stavamo preparando il materiale per ATS.\nAperto: la scheda cliente."):
    monkeypatch.setattr(riassunti, "chat", lambda s, u: testo)


# ══════════════════════════════════════════════════════════════════════════
# Si comprime UNA volta, a fine conversazione
# ══════════════════════════════════════════════════════════════════════════
def test_una_conversazione_diventa_un_promemoria(monkeypatch):
    _modello(monkeypatch)
    r = riassunti.comprimi("forma", "c1", TURNI)
    assert r and "ATS" in r["testo"]
    assert [x["conversazione"] for x in riassunti.elenco("forma")] == ["c1"]


def test_due_scambi_non_sono_una_conversazione(monkeypatch):
    """Sotto quattro turni non c'è niente da comprimere, e comprimere lo stesso
    vorrebbe dire riempire la pagina di promemoria che non dicono nulla."""
    _modello(monkeypatch)
    assert riassunti.comprimi("forma", "c1", TURNI[:2]) is None
    assert riassunti.elenco("forma") == []


def test_niente_da_ricordare_e_una_risposta_giusta(monkeypatch):
    _modello(monkeypatch, "NIENTE")
    assert riassunti.comprimi("forma", "c1", TURNI) is None


def test_un_riassunto_con_dati_personali_si_scarta(monkeypatch):
    """Si SCARTA, non si redige — come in learned.py. E qui pesa di più: una
    nota mutilata qualcuno la rilegge, un promemoria mai."""
    _modello(monkeypatch, "Andrea ha scritto a mario.rossi@ats.it per il preventivo.")
    assert riassunti.comprimi("forma", "c1", TURNI) is None


def test_ricomprimere_la_stessa_conversazione_non_ne_crea_due(monkeypatch):
    _modello(monkeypatch)
    riassunti.comprimi("forma", "c1", TURNI)
    riassunti.comprimi("forma", "c1", TURNI)
    assert len(riassunti.elenco("forma")) == 1


def test_il_modello_muto_non_rompe_niente(monkeypatch):
    monkeypatch.setattr(riassunti, "chat",
                        lambda s, u: (_ for _ in ()).throw(OSError("giù")))
    assert riassunti.comprimi("forma", "c1", TURNI) is None


# ══════════════════════════════════════════════════════════════════════════
# Limite 1 · Il riassunto NON allarga i permessi
# ══════════════════════════════════════════════════════════════════════════
def test_i_riassunti_non_escono_dal_tenant(monkeypatch):
    _modello(monkeypatch)
    riassunti.comprimi("forma", "c1", TURNI)
    assert riassunti.elenco("ats") == [] and riassunti.per_prompt("ats") == []


def test_uno_scope_nominato_ieri_non_da_diritti_oggi(client, monkeypatch):
    """Lo stesso test del filo (V7/A1), da questa porta. Il riassunto entra come
    contesto su cosa ci si è detti: i grant si ricalcolano SEMPRE dalla chiave."""
    _modello(monkeypatch, "Si parlava della cartella andrea-aloia e dei suoi contratti.")
    riassunti.comprimi("ats", "vecchia", TURNI)
    t = {"name": "ats", "allowed_scopes": ["ats"],
         "branding": {"tenant_code": "ats"}, "allowed_origins": [], "quota_day": None}
    monkeypatch.setattr(main.tenants, "get_tenant_by_key", lambda k: dict(t))
    monkeypatch.setattr(main.tenants, "quota_ok", lambda t2: True)
    visti = {}
    monkeypatch.setattr(main.rag, "answer",
                        lambda q, g, **kw: (visti.update({"grants": g, **kw}),
                                            {"answer": "ok", "sources": [], "scopes": []})[1])
    client.post("/chat", json={"message": "e i contratti?", "conversazione": "nuova"},
                headers={"X-Tenant-Key": "k"})
    grants = visti["grants"]
    piatti = grants if isinstance(grants, list) else sum((list(v) for v in grants.values()), [])
    assert set(piatti) == {"ats"} and "*" not in piatti and "andrea" not in piatti
    # il testo c'è come contesto, ma non è diventato un permesso
    assert any("andrea-aloia" in m for m in visti["memoria"])


def test_la_conversazione_in_corso_non_si_ricorda_da_sola(monkeypatch):
    """Il suo contesto è già il filo: rileggerle il proprio riassunto la farebbe
    girare su se stessa."""
    _modello(monkeypatch)
    riassunti.comprimi("forma", "c1", TURNI)
    assert riassunti.per_prompt("forma", escludi="c1") == []
    assert len(riassunti.per_prompt("forma", escludi="altra")) == 1


def test_se_ne_richiamano_pochi_non_tutti(monkeypatch):
    _modello(monkeypatch)
    for i in range(6):
        riassunti.comprimi("forma", f"c{i}", TURNI)
    assert len(riassunti.per_prompt("forma")) == riassunti.NEL_PROMPT


# ══════════════════════════════════════════════════════════════════════════
# Limite 2 · È un dato personale: retention, e il «Dimentica» ci arriva
# ══════════════════════════════════════════════════════════════════════════
def test_la_retention_si_applica_in_lettura_non_solo_a_parole(monkeypatch):
    """Una riga scaduta non deve comparire nemmeno se la pulizia non è ancora
    passata: è la differenza fra una promessa e un comportamento."""
    _modello(monkeypatch)
    r = riassunti.comprimi("forma", "vecchia", TURNI)
    for x in riassunti._mem:
        if x["id"] == r["id"]:
            x["created_at"] = time.time() - (riassunti.RETENTION_GIORNI + 1) * 86400
    assert riassunti.elenco("forma") == [] and riassunti.per_prompt("forma") == []


def test_dimenticare_un_riassunto_lo_cancella_davvero(monkeypatch):
    _modello(monkeypatch)
    r = riassunti.comprimi("forma", "c1", TURNI)
    assert riassunti.dimentica(r["id"]) is True
    assert riassunti.elenco("forma") == []
    assert riassunti.dimentica(r["id"]) is False        # lo dice, non finge


def test_il_bottone_della_pagina_raggiunge_i_riassunti(client, monkeypatch):
    """audit-2026-08-02-49. Se «Dimentica» non li raggiunge, l'art. 17 è coperto
    a metà — e mezza copertura, su un obbligo di legge, è peggio di niente."""
    _modello(monkeypatch)
    memoria.ricorda("forma", "Preferisci risposte brevi.", chiave="lunghezza", valore="breve")
    r = riassunti.comprimi("forma", "c1", TURNI)

    d = client.get("/admin/memoria?tenant=forma", headers=AUTH).json()
    assert d["totale"] == 1 and len(d["riassunti"]) == 1
    assert d["retention_riassunti"] == riassunti.RETENTION_GIORNI

    ok = client.post("/admin/memoria/dimentica", headers=AUTH,
                     json={"id": r["id"], "tipo": "riassunto", "by": "andrea"})
    assert ok.status_code == 200 and ok.json()["tipo"] == "riassunto"
    d2 = client.get("/admin/memoria?tenant=forma", headers=AUTH).json()
    assert d2["riassunti"] == [] and d2["totale"] == 1     # la memoria resta dov'era


def test_i_due_tipi_non_si_confondono(client, monkeypatch):
    _modello(monkeypatch)
    m = memoria.ricorda("forma", "Preferisci risposte brevi.")
    riassunti.comprimi("forma", "c1", TURNI)
    # un id di memoria chiesto come riassunto non deve cancellare niente
    assert client.post("/admin/memoria/dimentica", headers=AUTH,
                       json={"id": m["id"], "tipo": "riassunto"}).status_code == 404
    assert len(riassunti.elenco("forma")) == 1
    assert client.get("/admin/memoria?tenant=forma", headers=AUTH).json()["totale"] == 1


def test_dimenticare_tutto_di_un_tenant(monkeypatch):
    _modello(monkeypatch)
    for i in range(3):
        riassunti.comprimi("forma", f"c{i}", TURNI)
    assert riassunti.dimentica_tutto("forma") == 3
    assert riassunti.elenco("forma") == []


# ══════════════════════════════════════════════════════════════════════════
# La chiusura, dall'API
# ══════════════════════════════════════════════════════════════════════════
def _tenant(monkeypatch):
    # `_tenant_code` legge branding.tenant_code, poi il primo scope: qui si usa
    # la via esplicita, come in produzione per il tenant FORMA.
    t = {"name": "forma", "allowed_scopes": ["forma-core"],
         "branding": {"tenant_code": "forma"}, "allowed_origins": [], "quota_day": None}
    monkeypatch.setattr(main.tenants, "get_tenant_by_key", lambda k: dict(t))
    monkeypatch.setattr(main.tenants, "quota_ok", lambda t2: True)


def test_chiudere_la_conversazione_la_comprime_e_chiude_il_filo(client, monkeypatch):
    _tenant(monkeypatch)
    _modello(monkeypatch)
    filo.aggiungi("forma", "c1", [], "ciao", "ciao a te")
    r = client.post("/chat/chiudi", json={"conversazione": "c1", "history": TURNI},
                    headers={"X-Tenant-Key": "k"})
    assert r.status_code == 200 and r.json()["riassunto"] is True
    assert len(riassunti.elenco("forma")) == 1
    assert filo.rammenta("forma", "c1") == []      # il filo lungo si chiude qui


def test_chiudere_una_conversazione_vuota_lo_dice(client, monkeypatch):
    _tenant(monkeypatch)
    _modello(monkeypatch)
    r = client.post("/chat/chiudi", json={"conversazione": "c1", "history": TURNI[:2]},
                    headers={"X-Tenant-Key": "k"})
    assert r.json()["riassunto"] is False and r.json()["perche"]


def test_chiudere_vuole_una_chiave_valida(client, monkeypatch):
    monkeypatch.setattr(main.tenants, "get_tenant_by_key", lambda k: None)
    assert client.post("/chat/chiudi", json={"conversazione": "c1"},
                       headers={"X-Tenant-Key": "sbagliata"}).status_code == 401
