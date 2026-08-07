"""V7/A · Il filo della conversazione, le capacità, e il cerchio che si chiude.

Il test che conta più di tutti è l'ultimo: nessuno ha mai visto girare in fila
`gap → scrivo la nota dalla bolla → dopo l'ingest la stessa domanda ha risposta,
con la fonte che punta alla nota appena nata`. I tre pezzi esistevano da soli.
Qui il cerchio si percorre tutto, con un indice finto ma con il filtro dei
permessi VERO — perché è quello il punto in cui una scorciatoia si pagherebbe.
"""
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import filo, main, rag, security, tenants, writeback
from app.config import settings

client = TestClient(main.app)


# ══════════════════════════════════════════════════════════════════════════
# Un indice finto che rispetta DAVVERO il filtro dei grant.
#
# Non si finge `_retrieve` (sarebbe saltare proprio il pezzo da dimostrare): si
# finge il client Qdrant e si applica a mano la semantica di `build_filter`, così
# i test sui permessi passano dal filtro vero costruito da rag.
# ══════════════════════════════════════════════════════════════════════════
class IndiceFinto:
    def __init__(self, note=None):
        self.note = list(note or [])      # [{slug, scope, title, text}]
        self.ultimo_filtro = None

    def aggiungi(self, slug, scope, title, text):
        self.note.append({"slug": slug, "scope": scope, "title": title, "text": text})

    # ---- semantica minima del Filter di Qdrant, quanto basta per i grant ----
    @staticmethod
    def _cond_ok(nota, c):
        if hasattr(c, "should") or hasattr(c, "must"):        # Filter annidato
            return IndiceFinto._filtro_ok(nota, c)
        campo = {"scope": nota["scope"], "slug": nota["slug"]}.get(c.key)
        m = c.match
        if hasattr(m, "any"):
            return campo in m.any
        return campo == m.value

    @staticmethod
    def _filtro_ok(nota, f):
        if f is None:
            return True
        must = getattr(f, "must", None) or []
        should = getattr(f, "should", None) or []
        if must and not all(IndiceFinto._cond_ok(nota, c) for c in must):
            return False
        if should and not any(IndiceFinto._cond_ok(nota, c) for c in should):
            return False
        return True

    def query_points(self, collection_name=None, query=None, query_filter=None, limit=10):
        self.ultimo_filtro = query_filter
        parole = {w for w in str(query or "").lower().split() if len(w) > 3}
        punti = []
        for n in self.note:
            if not self._filtro_ok(n, query_filter):
                continue
            testo = f'{n["title"]} {n["text"]}'.lower()
            score = sum(1 for w in parole if w in testo) / max(1, len(parole))
            if score > 0:
                punti.append(SimpleNamespace(score=score, payload=dict(n)))
        punti.sort(key=lambda p: -p.score)
        return SimpleNamespace(points=punti[:limit])


@pytest.fixture()
def indice(monkeypatch):
    idx = IndiceFinto()
    monkeypatch.setattr(rag, "client", lambda: idx)
    # l'"embedding" è il testo stesso: così l'indice finto può cercare per parole
    monkeypatch.setattr(rag, "embed", lambda testi: [testi[0]])
    monkeypatch.setattr(settings, "retrieval_min_score", 0.0)
    monkeypatch.setattr(settings, "retrieval_rel_score", 0.0)
    monkeypatch.setattr(rag, "chat_con_uso", lambda s, u: ("risposta dal contenuto", None))
    filo.dimentica()
    yield idx
    filo.dimentica()


# ══════════════════════════════════════════════════════════════════════════
# A1 · Il filo
# ══════════════════════════════════════════════════════════════════════════
def test_finestra_a_caratteri_non_a_turni():
    """Sei turni sono tanti per iscritto e pochissimi a voce. Il budget in
    caratteri si adatta ai due modi di parlare senza doverli distinguere."""
    corti = [{"role": "user", "content": f"frase {i}"} for i in range(30)]
    assert len(filo.normalizza(corti)) == filo.MAX_TURNI      # tetto sui turni
    lunghi = [{"role": "user", "content": "x" * 1400} for _ in range(10)]
    tenuti = filo.normalizza(lunghi)
    assert 1 <= len(tenuti) <= 3                              # tetto sui caratteri
    assert sum(len(t["content"]) for t in tenuti) <= filo.MAX_CHARS + filo.MAX_CHARS_TURNO


def test_riconosce_la_domanda_di_seguito():
    turni = [{"role": "user", "content": "quanto fattura il cliente ATS?"}]
    for d in ["e per quell'altro cliente?", "torna a quello di prima",
              "no, intendevo l'altro", "e gli altri?", "invece a Centioni?"]:
        assert filo.e_di_seguito(d, turni), d


def test_una_domanda_che_si_regge_da_sola_non_si_espande():
    turni = [{"role": "user", "content": "quanto fattura ATS?"}]
    for d in ["quali sono gli orari del laboratorio di stampa 3D a Benevento?",
              "quanto costa la stampa 3D?", "ciao"]:
        assert filo.query_retrieval(d, turni) == d, d


def test_senza_filo_non_si_espande_niente():
    assert filo.query_retrieval("e per quell'altro?", []) == "e per quell'altro?"


def test_la_query_espansa_porta_il_soggetto_del_turno_prima():
    """È il cuore di A1: «e per quell'altro cliente?» da sola non somiglia a
    niente nel vault; con davanti il turno prima, sì."""
    turni = [{"role": "user", "content": "quanto fattura il cliente ATS?"},
             {"role": "assistant", "content": "ATS fattura 3.600 euro l'anno."}]
    q = filo.query_retrieval("e per quell'altro cliente?", turni)
    assert "ATS" in q and "quell'altro cliente" in q
    # le risposte di Divina restano FUORI: si cerca con le parole della persona
    assert "3.600" not in q


def test_memoria_server_solo_con_un_id():
    """Chi non dà un id non lascia niente sul server: il widget sul sito di un
    cliente resta apolide per costruzione."""
    turni = [{"role": "user", "content": "ciao"}]
    filo.ricorda("ats", "", turni)
    assert filo.rammenta("ats", "") == []
    filo.ricorda("ats", "conv-1", turni)
    assert len(filo.rammenta("ats", "conv-1")) == 1


def test_due_tenant_non_condividono_il_filo():
    filo.ricorda("ats", "conv-1", [{"role": "user", "content": "segreto di ATS"}])
    assert filo.rammenta("hrh", "conv-1") == []


def test_il_filo_scade(monkeypatch):
    filo.ricorda("ats", "conv-1", [{"role": "user", "content": "ciao"}])
    adesso = filo.time.time()                       # catturato PRIMA della patch
    monkeypatch.setattr(filo.time, "time", lambda: adesso + filo.TTL_S + 10)
    assert filo.rammenta("ats", "conv-1") == []


def test_la_history_del_client_vince_sulla_memoria():
    filo.ricorda("ats", "c", [{"role": "user", "content": "vecchio"}])
    turni, da = filo.risolvi([{"role": "user", "content": "nuovo"}], "ats", "c")
    assert da == "client" and turni[-1]["content"] == "nuovo"


def test_la_memoria_e_la_rete_quando_il_client_dimentica():
    filo.ricorda("ats", "c", [{"role": "user", "content": "vecchio"}])
    turni, da = filo.risolvi([], "ats", "c")
    assert da == "server" and turni[-1]["content"] == "vecchio"
    assert filo.risolvi([], "ats", "mai-vista") == ([], "nessuno")


# ── Il limite che non si supera: il filo NON allarga i permessi ──────────────
def test_il_filo_non_allarga_lo_scope(indice):
    """Un turno precedente che parla di un altro cliente non dà il diritto di
    leggerne le note: lo scope si ricalcola SEMPRE dai grant."""
    indice.aggiungi("scheda-ats", "ats", "Scheda ATS", "il fatturato di ATS e i contatti")
    indice.aggiungi("scheda-hrh", "hrh", "Scheda HRH", "il fatturato di HRH e i contatti")
    storia = [{"role": "user", "content": "parlami del cliente HRH e del suo fatturato"},
              {"role": "assistant", "content": "HRH è un cliente attivo."}]
    out = rag.answer("e il fatturato?", {"allowed_scopes": ["ats"]}, history=storia)
    slug = [s["slug"] for s in out["sources"]]
    assert slug == ["scheda-ats"]                 # HRH nominata nel filo, MAI restituita


def test_il_filtro_qdrant_e_identico_con_e_senza_filo(indice):
    """La prova diretta: la history entra nella QUERY, mai nel filtro."""
    indice.aggiungi("n", "ats", "Nota", "contenuto qualsiasi da cercare")
    rag.answer("contenuto", {"allowed_scopes": ["ats"]}, history=[])
    senza = indice.ultimo_filtro
    rag.answer("contenuto", {"allowed_scopes": ["ats"]},
               history=[{"role": "user", "content": "prima parlavamo di hrh e di forma-core"}])
    assert repr(indice.ultimo_filtro) == repr(senza)


def test_la_risposta_dichiara_quanto_filo_aveva(indice):
    """Un filo perso in silenzio era metà del problema: adesso si può dire."""
    indice.aggiungi("n", "ats", "Nota", "contenuto qualsiasi")
    out = rag.answer("contenuto", {"allowed_scopes": ["ats"]}, history=[])
    assert out["filo"] == {"turni": 0, "espansa": False}
    out = rag.answer("e quello?", {"allowed_scopes": ["ats"]},
                     history=[{"role": "user", "content": "il contenuto della nota"}])
    assert out["filo"]["turni"] == 1 and out["filo"]["espansa"] is True


def test_chat_passa_il_filo_e_la_provenienza(monkeypatch):
    monkeypatch.setattr(security, "origin_allowed", lambda o, a: True)
    monkeypatch.setattr(main, "rate_ok", lambda k: True)
    monkeypatch.setattr(tenants, "get_tenant_by_key",
                        lambda k: {"name": "ATS", "allowed_origins": [],
                                   "allowed_scopes": ["ats"], "branding": {"tenant_code": "ats"}})
    monkeypatch.setattr(rag, "answer",
                        lambda q, g, **kw: {"answer": "ok", "sources": [], "scopes": [],
                                            "filo": {"turni": len(kw.get("history") or []),
                                                     "espansa": False}})
    filo.dimentica()
    r1 = client.post("/chat", headers={"X-Tenant-Key": "K"},
                     json={"message": "primo", "conversazione": "c1",
                           "history": [{"role": "user", "content": "zero"}]})
    assert r1.json()["filo"]["da"] == "client"
    # secondo turno SENZA history: la rete di sicurezza server-side la ritrova
    r2 = client.post("/chat", headers={"X-Tenant-Key": "K"},
                     json={"message": "secondo", "conversazione": "c1"})
    assert r2.json()["filo"]["da"] == "server" and r2.json()["filo"]["turni"] >= 2
    # senza id, invece, il server non ha tenuto niente
    r3 = client.post("/chat", headers={"X-Tenant-Key": "K"}, json={"message": "terzo"})
    assert r3.json()["filo"]["da"] == "nessuno"
    filo.dimentica()


# ══════════════════════════════════════════════════════════════════════════
# A2 · Chiedere di FARE (lato motore: riconoscere che è un compito)
# ══════════════════════════════════════════════════════════════════════════
def test_riconosce_i_compiti_chiesti_come_parlano_le_persone():
    from app import agents_bridge as ab
    for t in ["prepara i solleciti", "mi prepari i solleciti delle fatture?",
              "puoi scrivere la mail al cliente?", "potresti riassumere la nota ATS?",
              "per favore genera il report"]:
        assert ab.is_task_like(t), t


def test_una_domanda_resta_una_domanda():
    from app import agents_bridge as ab
    for t in ["quali servizi offre FORMA?", "ciao come stai", "quanto costa la stampa 3d",
              "mi dici gli orari?", "dove siete?"]:
        assert not ab.is_task_like(t), t


# ══════════════════════════════════════════════════════════════════════════
# A3 · IL CERCHIO — nessuno l'aveva mai visto girare tutto
# ══════════════════════════════════════════════════════════════════════════
def test_il_cerchio_si_chiude(indice, monkeypatch, tmp_path):
    """domanda senza risposta → `gap` → scrivo la nota dalla bolla → «ingest» →
    la STESSA domanda ha risposta, con la fonte che punta alla nota appena nata.

    È la dimostrazione del prodotto: non «l'AI che risponde», ma un cervello che
    cresce mentre lo usi. I tre pezzi esistevano da soli dal V6; questo è il
    primo test che li percorre in fila."""
    monkeypatch.setattr(settings, "vault_path", str(tmp_path))
    monkeypatch.setattr(security, "origin_allowed", lambda o, a: True)
    monkeypatch.setattr(main, "rate_ok", lambda k: True)
    monkeypatch.setattr(tenants, "get_tenant_by_key",
                        lambda k: {"name": "ATS", "allowed_origins": [], "key_hash": "h",
                                   "allowed_scopes": ["ats"], "branding": {"tenant_code": "ats"}})
    monkeypatch.setattr(tenants, "log_access", lambda *a, **k: None)
    monkeypatch.setattr(settings, "auto_reingest", False)
    H = {"X-Tenant-Key": "K"}
    DOMANDA = "quali sono gli orari del ritiro a domicilio nel weekend?"

    # 1 · Il cervello non sa, e lo dice APRENDO invece di chiudere.
    r1 = client.post("/chat", json={"message": DOMANDA, "conversazione": "cerchio"}, headers=H).json()
    assert r1["answer"] == rag.NO_ANSWER
    assert r1["sources"] == []
    assert r1["gap"]["question"] == DOMANDA          # il titolo pronto per la nota
    assert r1["gap"]["offer"]                        # e l'offerta di scriverla

    # 2 · La nota si scrive dalla bolla: due tempi, e senza conferma non succede niente.
    corpo = "Il ritiro a domicilio nel weekend copre solo il centro, dalle 9 alle 13."
    prev = client.post("/writeback", headers=H, json={
        "scope": "ats", "title": r1["gap"]["question"], "body": corpo,
        "origin": "conversazione", "confirm": False}).json()
    assert prev["consolidato"] is False
    assert "NON verificato" in prev["preview"]["content"]   # il server marca, non il client
    assert not list(tmp_path.rglob("*.md"))          # anteprima = nessuna scrittura

    res = client.post("/writeback", headers=H, json={
        "scope": "ats", "title": r1["gap"]["question"], "body": corpo,
        "origin": "conversazione", "confirm": True}).json()
    assert res["consolidato"] is True
    scritta = (tmp_path / res["path"]).read_text("utf-8")
    assert "Origine: conversazione con Divina" in scritta and "NON verificato" in scritta

    # 3 · L'ingest indicizza la nota appena nata (qui: l'indice finto la riceve).
    indice.aggiungi(res["slug"], "ats", r1["gap"]["question"], corpo)

    # 4 · La stessa domanda, adesso, ha risposta — e la fonte è QUELLA nota.
    r2 = client.post("/chat", json={"message": DOMANDA, "conversazione": "cerchio"}, headers=H).json()
    assert r2["answer"] != rag.NO_ANSWER
    assert "gap" not in r2                            # il buco non c'è più
    assert [s["slug"] for s in r2["sources"]] == [res["slug"]]

    # 5 · E il cerchio non ha allargato niente: un altro tenant non la vede.
    monkeypatch.setattr(tenants, "get_tenant_by_key",
                        lambda k: {"name": "HRH", "allowed_origins": [], "key_hash": "h2",
                                   "allowed_scopes": ["hrh"], "branding": {"tenant_code": "hrh"}})
    r3 = client.post("/chat", json={"message": DOMANDA}, headers=H).json()
    assert r3["answer"] == rag.NO_ANSWER and r3["sources"] == []
