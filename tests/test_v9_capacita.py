"""V9/C · Le capacità si raggiungono dalla conversazione (audit-2026-07-31-06).

Aperta dal 31 luglio. Le 42 skill esistono, la Squadra le mostra, Caronte ha la
sua — e dalla chat non ci si arriva, perché `rag.py` non le nomina mai.

Il criterio, che è anche quello che rende insufficiente il riconoscimento a
parole: **una capacità esiste quando qualcuno può usarla senza sapere come si
chiama.** Chi scrive «cerca chi vende stampa 3D a Benevento» non deve sapere che
la skill si chiama `customer-research` — e quelle due frasi non hanno una parola
in comune.

Il vincolo, che non si tocca: qui si OFFRE, non si esegue.
"""
import pytest
from fastapi.testclient import TestClient

from app import agents_bridge, main, rag
from app.config import settings

TOK = "tok-di-test-lungo-abbastanza-123456"

# Un catalogo finto ma della forma vera di /agents.
CATALOGO = [
    {"agente": "beatrice", "skill": "customer-research", "role": "Customer Research",
     "desc": "trova e qualifica potenziali clienti, studia il mercato attorno",
     "parole": agents_bridge._parole("customer research trova qualifica potenziali clienti mercato")},
    {"agente": "dante", "skill": "invoice-chase", "role": "Invoice Chase",
     "desc": "prepara i solleciti per le fatture scadute",
     "parole": agents_bridge._parole("invoice chase solleciti fatture scadute pagamenti")},
    {"agente": "virgilio", "skill": "review-contract", "role": "Review Contract",
     "desc": "legge un contratto e segnala le clausole rischiose",
     "parole": agents_bridge._parole("review contract contratto clausole rischiose legale")},
]


@pytest.fixture(autouse=True)
def _pulizia():
    agents_bridge.reset_catalogo()
    yield
    agents_bridge.reset_catalogo()


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(settings, "admin_token", TOK)
    return TestClient(main.app)


# ── un embedding finto ma con una geometria vera ─────────────────────────────
# Ogni testo diventa un punto su un cerchio in base al TEMA che contiene: due
# frasi dello stesso tema sono vicine anche senza parole in comune, che è
# esattamente la cosa che qui va provata.
_TEMI = {
    "clienti": ("cerca", "trova", "vende", "compr", "client", "mercat", "potenzial",
                "customer", "research", "qualifica", "concorren"),
    "soldi": ("fattur", "sollecit", "pagat", "pagament", "scadut", "invoice", "chase", "incass"),
    "legale": ("contratt", "accordo", "clausol", "legale", "review", "rischios", "firm"),
}


def _finto_embed(testi):
    import math
    out = []
    for t in testi:
        low = t.lower()
        punti = {k: sum(1 for r in rs if r in low) for k, rs in _TEMI.items()}
        tema = max(punti, key=punti.get) if any(punti.values()) else ""
        ang = {"clienti": 0.0, "soldi": 2.0, "legale": 4.0}.get(tema, 3.0)
        out.append([math.cos(ang), math.sin(ang), 0.05 if tema else 0.9])
    return out


# ══════════════════════════════════════════════════════════════════════════
# Il cuore: senza sapere come si chiama
# ══════════════════════════════════════════════════════════════════════════
def test_le_parole_da_sole_NON_bastano_ed_e_il_motivo_del_vettore():
    """La prova che il riconoscitore lessicale del V7 non poteva soddisfare il
    criterio: «cerca chi vende stampa 3D a Benevento» e «trova e qualifica
    potenziali clienti» condividono UNA parola. Contarle vorrebbe dire chiedere
    all'utente di indovinare il vocabolario della skill — cioè il nome, scritto
    peggio."""
    assert agents_bridge.trova("cerca chi vende stampa 3D a Benevento", CATALOGO) is None


def test_col_vettore_ci_arriva(monkeypatch):
    """Lo stesso messaggio, con il vettore che il retrieval ha già calcolato."""
    monkeypatch.setattr("app.providers.embed", _finto_embed)
    qvec = _finto_embed(["cerca chi vende stampa 3D a Benevento"])[0]
    c = agents_bridge.trova("cerca chi vende stampa 3D a Benevento", list(CATALOGO), qvec=qvec)
    assert c and c["skill"] == "customer-research" and c["come"] == "significato"


def test_il_vettore_sceglie_la_capacita_giusta_fra_tante(monkeypatch):
    monkeypatch.setattr("app.providers.embed", _finto_embed)
    prove = [("mi prepari i solleciti per chi non ha ancora pagato?", "invoice-chase"),
             ("dai un'occhiata a questo accordo prima che lo firmi", "review-contract"),
             ("chi potrebbe comprare da noi in provincia?", "customer-research")]
    for domanda, atteso in prove:
        c = agents_bridge.trova(domanda, list(CATALOGO), qvec=_finto_embed([domanda])[0])
        assert c and c["skill"] == atteso, domanda


def test_una_domanda_qualunque_non_suggerisce_niente(monkeypatch):
    """La soglia è severa apposta: un suggerimento sbagliato sotto ogni risposta
    diventa rumore, e il rumore si impara a ignorare."""
    monkeypatch.setattr("app.providers.embed", _finto_embed)
    d = "che tempo fa domani a Napoli"
    assert agents_bridge.trova(d, list(CATALOGO), qvec=_finto_embed([d])[0]) is None


def test_col_vettore_non_si_ripiega_sulle_parole(monkeypatch):
    """Se il vettore ha guardato e ha detto di no, contare le parole dopo
    sarebbe cercare un sì finché non arriva."""
    monkeypatch.setattr("app.providers.embed", _finto_embed)
    d = "quali clienti mercato potenziali"          # tante parole in comune
    q = _finto_embed(["argomento del tutto diverso"])[0]
    assert agents_bridge.trova(d, list(CATALOGO), qvec=q) is None


def test_senza_vettore_le_parole_restano_la_rete(monkeypatch):
    """Embedding non disponibile: peggio, ma non muto."""
    c = agents_bridge.trova("prepara i solleciti per le fatture scadute", CATALOGO)
    assert c and c["skill"] == "invoice-chase" and c["come"] == "parole"


# ══════════════════════════════════════════════════════════════════════════
# Il catalogo non si duplica
# ══════════════════════════════════════════════════════════════════════════
def test_il_catalogo_si_legge_dall_orchestratore_e_si_tiene_in_ram(monkeypatch):
    chiamate = []

    class R:
        @staticmethod
        def raise_for_status():
            pass

        @staticmethod
        def json():
            return {"agents": [{"id": "dante", "skills": [
                        {"id": "invoice-chase", "role": "Invoice Chase",
                         "desc": "solleciti", "department": "BIZ"}]}],
                    "subagents": [{"id": "caronte", "sotto": "beatrice", "skills": [
                        {"id": "ricerca-clienti", "role": "Ricerca clienti", "desc": "trova"}]}]}

    monkeypatch.setattr(settings, "agents_bridge", True)
    monkeypatch.setattr(settings, "divina_url", "https://orch")
    monkeypatch.setattr(settings, "divina_admin_token", "t")
    monkeypatch.setattr(agents_bridge.httpx, "get",
                        lambda *a, **k: chiamate.append(1) or R())
    c1 = agents_bridge.catalogo()
    c2 = agents_bridge.catalogo()
    assert len(c1) == 2 and len(chiamate) == 1        # la seconda volta non richiama
    assert {x["agente"] for x in c1} == {"dante", "beatrice"}   # il sub sta sotto il suo


def test_orchestratore_giu_non_e_un_errore_in_chat(monkeypatch):
    monkeypatch.setattr(settings, "agents_bridge", True)
    monkeypatch.setattr(settings, "divina_url", "https://orch")
    monkeypatch.setattr(settings, "divina_admin_token", "t")
    monkeypatch.setattr(agents_bridge.httpx, "get",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("giù")))
    assert agents_bridge.catalogo() == []
    assert agents_bridge.trova("prepara i solleciti") is None


def test_ponte_spento_non_fa_nessuna_chiamata(monkeypatch):
    monkeypatch.setattr(settings, "agents_bridge", False)
    monkeypatch.setattr(agents_bridge.httpx, "get",
                        lambda *a, **k: pytest.fail("nessuna chiamata col ponte spento"))
    assert agents_bridge.catalogo() == []


# ══════════════════════════════════════════════════════════════════════════
# Nel PROMPT, perché a voce un chip non si clicca
# ══════════════════════════════════════════════════════════════════════════
def test_la_capacita_entra_nella_frase_e_dice_di_non_eseguire():
    p = rag._system("it", capacita={"agente": "dante", "role": "Invoice Chase"})
    assert "CAPACITÀ DISPONIBILE" in p and "dante" in p and "Invoice Chase" in p
    assert "OFFRIRE" in p
    assert "Non dire mai" in p and "in attesa di approvazione" in p


def test_senza_capacita_il_prompt_e_identico():
    assert rag._system("it", capacita=None) == rag._system("it")
    assert rag._system("it", capacita={"agente": "", "role": ""}) == rag._system("it")


def test_la_capacita_non_e_un_permesso():
    """Offrire non allarga niente: il blocco è testo di TONO, e i vincoli di
    scope e provenienza restano dov'erano."""
    p = rag._system("it", capacita={"agente": "dante", "role": "Invoice Chase"})
    base = rag._system("it")
    assert base in p and len(p) > len(base)
    assert "⟦fuori⟧" not in p            # nessuna deroga di provenienza comparsa


# ══════════════════════════════════════════════════════════════════════════
# Il giro completo su /chat
# ══════════════════════════════════════════════════════════════════════════
def _tenant(monkeypatch):
    t = {"name": "forma", "tenant_code": "forma", "allowed_scopes": ["forma-core"],
         "branding": {}, "allowed_origins": [], "quota_day": None}
    monkeypatch.setattr(main.tenants, "get_tenant_by_key", lambda k: dict(t))
    monkeypatch.setattr(main.tenants, "quota_ok", lambda t2: True)


def test_chat_offre_la_capacita_e_la_restituisce_come_dato(client, monkeypatch):
    _tenant(monkeypatch)
    monkeypatch.setattr(settings, "agents_bridge", True)
    monkeypatch.setattr(settings, "divina_url", "https://orch")
    monkeypatch.setattr(settings, "divina_admin_token", "t")
    monkeypatch.setattr(settings, "agents_auto", False)
    monkeypatch.setattr("app.providers.embed", _finto_embed)
    monkeypatch.setattr(main.rag, "vettore", lambda q: _finto_embed([q])[0])
    monkeypatch.setattr(agents_bridge, "catalogo", lambda *a, **k: [dict(c) for c in CATALOGO])
    visti = {}
    monkeypatch.setattr(main.rag, "answer",
                        lambda q, g, **kw: (visti.update(kw),
                                            {"answer": "ok", "sources": [], "scopes": []})[1])
    r = client.post("/chat", json={"message": "cerca chi vende stampa 3D a Benevento"},
                    headers={"X-Tenant-Key": "k"})
    assert r.status_code == 200
    # 1 · è arrivata al modello, quindi anche a voce la risposta può nominarla
    assert visti["capacita"]["skill"] == "customer-research"
    # 2 · e torna come dato, per il bottone nella console e nel widget
    c = r.json()["capacita"]
    assert c["agente"] == "beatrice" and c["role"] == "Customer Research"
    assert "punti" not in c and "quanto" not in c       # il punteggio non è roba da mostrare


def test_col_ponte_spento_chat_e_identico_a_prima(client, monkeypatch):
    """Nessuna chiamata, nessun campo nuovo: la capability resta OPT-IN."""
    _tenant(monkeypatch)
    monkeypatch.setattr(settings, "agents_bridge", False)
    monkeypatch.setattr(main.rag, "vettore",
                        lambda q: pytest.fail("nessuna embedding in più col ponte spento"))
    visti = {}
    monkeypatch.setattr(main.rag, "answer",
                        lambda q, g, **kw: (visti.update(kw),
                                            {"answer": "ok", "sources": [], "scopes": []})[1])
    r = client.post("/chat", json={"message": "prepara i solleciti"},
                    headers={"X-Tenant-Key": "k"})
    assert visti["capacita"] is None and "capacita" not in r.json()


def test_offrire_non_esegue_niente(client, monkeypatch):
    """Il vincolo del V5c, riprovato da questa porta: suggerire una capacità non
    accoda nessuna azione. Porta principale e porta di servizio restano chiuse."""
    _tenant(monkeypatch)
    monkeypatch.setattr(settings, "agents_bridge", True)
    monkeypatch.setattr(settings, "divina_url", "https://orch")
    monkeypatch.setattr(settings, "divina_admin_token", "t")
    monkeypatch.setattr(settings, "agents_auto", False)
    monkeypatch.setattr("app.providers.embed", _finto_embed)
    monkeypatch.setattr(main.rag, "vettore", lambda q: _finto_embed([q])[0])
    monkeypatch.setattr(agents_bridge, "catalogo", lambda *a, **k: [dict(c) for c in CATALOGO])
    monkeypatch.setattr(agents_bridge, "route",
                        lambda *a, **k: pytest.fail("suggerire NON deve instradare"))
    monkeypatch.setattr(main.rag, "answer",
                        lambda q, g, **kw: {"answer": "ok", "sources": [], "scopes": []})
    accodate = []
    monkeypatch.setattr(main.braintasks, "add",
                        lambda *a, **k: accodate.append(a) or None)
    r = client.post("/chat", json={"message": "cerca chi potrebbe comprare da noi"},
                    headers={"X-Tenant-Key": "k"})
    assert r.status_code == 200 and r.json().get("capacita")
    assert accodate == []
