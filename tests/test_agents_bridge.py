"""Ponte Divina → agenti Divina (ovy-orchestrator): capability OPT-IN, OFF di default.

Tutto offline: httpx (verso Divina) e il retrieval Qdrant/LLM del RAG sono mockati.
Verifica i requisiti non negoziabili:
  - OFF di default: con ponte disattivo o senza config /chat è identico a oggi (RAG),
    NESSUNA chiamata a Divina;
  - ON + agent:true (o euristico con AGENTS_AUTO) → instrada a Divina e ritorna l'output
    dell'agente in `answer` + una fonte di tipo `agent` (+ eventuali web_sources);
  - a Divina passa SOLO il tenant_code (mai i grant): lo scope/filtro Qdrant NON cambia;
  - Divina irraggiungibile o routed:false → fallback pulito al RAG, mai un errore secco.
"""
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app import rag, main, tenants, security, agents_bridge
from app.config import settings

client = TestClient(main.app)


def _hit(slug="nota-x", text="contenuto del cervello"):
    return SimpleNamespace(score=0.9, payload={"slug": slug, "text": text})


_ROUTED = {"routed": True, "agent": "virgilio", "skill": "review-contract",
           "output": "Ecco la bozza richiesta.", "confidence": 0.82,
           "web_sources": [{"type": "web", "title": "Fonte", "url": "https://x.tld"}]}


# ── enabled(): gating a tre condizioni (flag + url + token) ────────────────────
def test_enabled_richiede_flag_e_config(monkeypatch):
    monkeypatch.setattr(settings, "agents_bridge", True)
    monkeypatch.setattr(settings, "divina_url", "https://divina.tld")
    monkeypatch.setattr(settings, "divina_admin_token", "tok")
    assert agents_bridge.enabled() is True
    # manca un pezzo qualsiasi → inerte
    monkeypatch.setattr(settings, "agents_bridge", False)
    assert agents_bridge.enabled() is False
    monkeypatch.setattr(settings, "agents_bridge", True)
    monkeypatch.setattr(settings, "divina_url", "")
    assert agents_bridge.enabled() is False
    monkeypatch.setattr(settings, "divina_url", "https://divina.tld")
    monkeypatch.setattr(settings, "divina_admin_token", "")
    assert agents_bridge.enabled() is False


# ── route(): INERTE senza config → nessuna chiamata di rete ───────────────────
def test_route_inerte_senza_config(monkeypatch):
    monkeypatch.setattr(settings, "agents_bridge", False)

    def boom(*a, **k):
        raise AssertionError("nessuna chiamata a Divina col ponte OFF")
    monkeypatch.setattr(agents_bridge.httpx, "post", boom)
    assert agents_bridge.route("ats", "scrivi un contratto") is None


def test_route_inerte_senza_tenant_code(monkeypatch):
    monkeypatch.setattr(settings, "agents_bridge", True)
    monkeypatch.setattr(settings, "divina_url", "https://divina.tld")
    monkeypatch.setattr(settings, "divina_admin_token", "tok")

    def boom(*a, **k):
        raise AssertionError("nessuna chiamata a Divina senza tenant_code")
    monkeypatch.setattr(agents_bridge.httpx, "post", boom)
    assert agents_bridge.route("", "scrivi qualcosa") is None
    assert agents_bridge.route("ats", "   ") is None


# ── route(): ON → chiama Divina col payload giusto (solo tenant_code + Bearer) ─
def test_route_chiama_divina_payload_e_bearer(monkeypatch):
    monkeypatch.setattr(settings, "agents_bridge", True)
    monkeypatch.setattr(settings, "divina_url", "https://divina.tld/")
    monkeypatch.setattr(settings, "divina_admin_token", "seg-tok")
    seen = {}

    class _R:
        def raise_for_status(self): pass
        def json(self): return _ROUTED

    def fake_post(url, json=None, headers=None, timeout=None):
        seen.update(url=url, json=json, headers=headers)
        return _R()
    monkeypatch.setattr(agents_bridge.httpx, "post", fake_post)

    out = agents_bridge.route("ats", "prepara una nota", history=[{"role": "user", "content": "x"}])
    assert out == _ROUTED
    assert seen["url"] == "https://divina.tld/agents/route"          # no doppio slash
    assert seen["headers"]["Authorization"] == "Bearer seg-tok"
    # SICUREZZA scope: a Divina passa SOLO il tenant_code, mai i grant/allowed_scopes.
    assert seen["json"]["tenant"] == "ats"
    assert seen["json"]["input"] == "prepara una nota"
    assert "allowed_scopes" not in seen["json"] and "grants" not in seen["json"]
    # senza companion esplicito il campo `agent` NON viaggia (payload storico invariato)
    assert "agent" not in seen["json"]
    # col companion dal selettore in console il campo viaggia (l'orchestratore datato
    # lo ignora: additivo, mai rompente)
    agents_bridge.route("ats", "prepara una nota", agent="dante")
    assert seen["json"]["agent"] == "dante"


def test_route_errore_rete_ritorna_none(monkeypatch):
    monkeypatch.setattr(settings, "agents_bridge", True)
    monkeypatch.setattr(settings, "divina_url", "https://divina.tld")
    monkeypatch.setattr(settings, "divina_admin_token", "tok")

    def boom(*a, **k):
        raise RuntimeError("timeout")
    monkeypatch.setattr(agents_bridge.httpx, "post", boom)
    assert agents_bridge.route("ats", "genera report") is None       # assorbito → fallback


# ── is_task_like(): euristico verbi imperativi ────────────────────────────────
def test_is_task_like_riconosce_i_compiti():
    for m in ("scrivi un contratto", "Analizza questi dati", "  PREPARA la busta paga",
              "genera un report", "crea una campagna", "Riassumi il documento."):
        assert agents_bridge.is_task_like(m) is True


def test_is_task_like_ignora_le_domande():
    for m in ("qual è il fatturato?", "come funziona il contratto",
              "puoi dirmi il margine", "", "   ", "chi è Andrea"):
        assert agents_bridge.is_task_like(m) is False


# ── /chat end-to-end: setup tenant + mock RAG ─────────────────────────────────
def _mock_tenant(monkeypatch, branding=None, scopes=None):
    t = {"name": "Cliente", "allowed_scopes": scopes if scopes is not None else ["ats"],
         "allowed_origins": [], "branding": branding or {}}
    monkeypatch.setattr(tenants, "get_tenant_by_key", lambda k: t)
    monkeypatch.setattr(security, "origin_allowed", lambda o, a: True)
    monkeypatch.setattr(main, "rate_ok", lambda k: True)
    monkeypatch.setattr(tenants, "quota_ok", lambda t: True)
    return t


def _mock_rag(monkeypatch, capture=None):
    """RAG mockato (nessuna rete). Se `capture` è un dict, registra i grant visti."""
    def fake_retrieve(q, g, k):
        if capture is not None:
            capture["grants"] = g
        return [_hit()]
    monkeypatch.setattr(rag, "_retrieve", fake_retrieve)
    monkeypatch.setattr(rag, "chat", lambda s, u: "risposta-rag")


# ── Ponte OFF (default): agent:true → RAG normale, nessuna chiamata a Divina ───
def test_chat_ponte_off_default_nessuna_chiamata_a_divina(monkeypatch):
    _mock_tenant(monkeypatch)
    monkeypatch.setattr(settings, "agents_bridge", False)     # ponte OFF (default)
    _mock_rag(monkeypatch)

    def no_call(*a, **k):
        raise AssertionError("nessun instradamento a Divina col ponte OFF")
    monkeypatch.setattr(agents_bridge, "route", no_call)

    r = client.post("/chat", json={"message": "scrivi un contratto", "agent": True},
                    headers={"X-Tenant-Key": "K"})
    assert r.status_code == 200
    body = r.json()
    assert body["answer"] == "risposta-rag"
    assert body["sources"] == ["nota-x"]                       # pure stringhe → identico a oggi


def test_chat_ponte_attivo_ma_senza_config_e_inerte(monkeypatch):
    """AGENTS_BRIDGE=true ma DIVINA_URL/token vuoti → inerte, nessuna chiamata."""
    _mock_tenant(monkeypatch)
    monkeypatch.setattr(settings, "agents_bridge", True)
    monkeypatch.setattr(settings, "divina_url", "")
    monkeypatch.setattr(settings, "divina_admin_token", "")
    _mock_rag(monkeypatch)

    def no_net(*a, **k):
        raise AssertionError("nessuna chiamata di rete senza DIVINA_URL/token")
    monkeypatch.setattr(agents_bridge.httpx, "post", no_net)

    r = client.post("/chat", json={"message": "genera report", "agent": True},
                    headers={"X-Tenant-Key": "K"})
    assert r.status_code == 200
    assert r.json()["answer"] == "risposta-rag"                 # RAG, non l'agente


# ── Ponte ON + agent:true → instrada a Divina e ne ritorna l'output ───────────
def _enable_bridge(monkeypatch):
    monkeypatch.setattr(settings, "agents_bridge", True)
    monkeypatch.setattr(settings, "divina_url", "https://divina.tld")
    monkeypatch.setattr(settings, "divina_admin_token", "tok")


def test_chat_ponte_on_instrada_e_ritorna_output_agente(monkeypatch):
    _mock_tenant(monkeypatch)
    _enable_bridge(monkeypatch)
    seen = {}

    def fake_route(tenant_code, message, history=None, **k):
        seen.update(tenant_code=tenant_code, message=message)
        return _ROUTED
    monkeypatch.setattr(agents_bridge, "route", fake_route)

    def no_rag(*a, **k):
        raise AssertionError("il RAG non deve essere invocato quando si instrada")
    monkeypatch.setattr(rag, "_retrieve", no_rag)

    r = client.post("/chat", json={"message": "prepara un contratto", "agent": True},
                    headers={"X-Tenant-Key": "K"})
    assert r.status_code == 200
    body = r.json()
    # output dell'agente come answer
    assert body["answer"] == "Ecco la bozza richiesta."
    # sources: una voce di tipo agent (agente/skill) + le web_sources di Divina
    agent_src = body["sources"][0]
    assert agent_src["type"] == "agent"
    assert agent_src["agent"] == "virgilio" and agent_src["skill"] == "review-contract"
    assert {"type": "web", "title": "Fonte", "url": "https://x.tld"} in body["sources"]
    # SICUREZZA scope: a route passa SOLO il tenant_code (primo allowed_scope), non i grant.
    assert seen["tenant_code"] == "ats"


def test_chat_tenant_code_da_branding_override(monkeypatch):
    """branding.tenant_code ha la precedenza sul primo allowed_scope."""
    _mock_tenant(monkeypatch, branding={"tenant_code": "forma-core"}, scopes=["ats", "hrh"])
    _enable_bridge(monkeypatch)
    seen = {}
    monkeypatch.setattr(agents_bridge, "route",
                        lambda tc, m, history=None, **k: seen.update(tc=tc) or _ROUTED)
    r = client.post("/chat", json={"message": "analizza", "agent": True},
                    headers={"X-Tenant-Key": "K"})
    assert r.status_code == 200
    assert seen["tc"] == "forma-core"


# ── Selettore companion in console: companion → implica agent + viaggia a Divina ──
def test_chat_companion_implica_agent_e_viaggia(monkeypatch):
    _mock_tenant(monkeypatch)
    _enable_bridge(monkeypatch)
    seen = {}
    monkeypatch.setattr(agents_bridge, "route",
                        lambda tc, m, history=None, agent=None, **k:
                        seen.update(agent=agent) or _ROUTED)
    # SENZA flag agent:true — basta il companion per instradare
    r = client.post("/chat", json={"message": "come sta la cassa?",
                                   "companion": "Dante"},
                    headers={"X-Tenant-Key": "K"})
    assert r.status_code == 200
    assert r.json()["answer"] == "Ecco la bozza richiesta."
    assert seen["agent"] == "dante"                     # normalizzato lowercase


def test_chat_companion_ignoto_resta_rag(monkeypatch):
    """Companion non valido → ignorato: senza flag agent il RAG risponde come sempre."""
    _mock_tenant(monkeypatch)
    _enable_bridge(monkeypatch)
    _mock_rag(monkeypatch)
    monkeypatch.setattr(agents_bridge, "route", lambda *a, **k:
                        (_ for _ in ()).throw(AssertionError("non deve instradare")))
    r = client.post("/chat", json={"message": "ciao", "companion": "gandalf"},
                    headers={"X-Tenant-Key": "K"})
    assert r.status_code == 200
    assert r.json()["answer"] == "risposta-rag"


# ── Fallback pulito al RAG: Divina irraggiungibile o routed:false ─────────────
def test_chat_divina_irraggiungibile_fallback_rag(monkeypatch):
    _mock_tenant(monkeypatch)
    _enable_bridge(monkeypatch)
    _mock_rag(monkeypatch)
    monkeypatch.setattr(agents_bridge, "route", lambda *a, **k: None)   # irraggiungibile

    r = client.post("/chat", json={"message": "scrivi", "agent": True},
                    headers={"X-Tenant-Key": "K"})
    assert r.status_code == 200                                          # mai errore secco
    assert r.json()["answer"] == "risposta-rag"


def test_chat_routed_false_fallback_rag(monkeypatch):
    _mock_tenant(monkeypatch)
    _enable_bridge(monkeypatch)
    _mock_rag(monkeypatch)
    monkeypatch.setattr(agents_bridge, "route",
                        lambda *a, **k: {"routed": False, "suggestion": "riformula"})

    r = client.post("/chat", json={"message": "scrivi", "agent": True},
                    headers={"X-Tenant-Key": "K"})
    assert r.status_code == 200
    assert r.json()["answer"] == "risposta-rag"                          # fallback al RAG


# ── Senza flag agent → RAG (anche col ponte ON): retro-compat ─────────────────
def test_chat_senza_flag_agent_resta_rag(monkeypatch):
    _mock_tenant(monkeypatch)
    _enable_bridge(monkeypatch)
    _mock_rag(monkeypatch)

    def no_call(*a, **k):
        raise AssertionError("senza agent:true (e AGENTS_AUTO off) non si instrada")
    monkeypatch.setattr(agents_bridge, "route", no_call)
    monkeypatch.setattr(settings, "agents_auto", False)

    r = client.post("/chat", json={"message": "scrivi un contratto"},
                    headers={"X-Tenant-Key": "K"})
    assert r.status_code == 200
    assert r.json()["sources"] == ["nota-x"]                             # RAG puro


# ── AGENTS_AUTO: auto-instradamento sui messaggi task-like ────────────────────
def test_chat_agents_auto_instrada_i_compiti(monkeypatch):
    _mock_tenant(monkeypatch)
    _enable_bridge(monkeypatch)
    monkeypatch.setattr(settings, "agents_auto", True)
    monkeypatch.setattr(agents_bridge, "route", lambda *a, **k: _ROUTED)

    def no_rag(*a, **k):
        raise AssertionError("un compito con AGENTS_AUTO va all'agente, non al RAG")
    monkeypatch.setattr(rag, "_retrieve", no_rag)

    # niente flag agent nel body: è l'euristico ad auto-instradare
    r = client.post("/chat", json={"message": "scrivi un contratto"},
                    headers={"X-Tenant-Key": "K"})
    assert r.status_code == 200
    assert r.json()["answer"] == "Ecco la bozza richiesta."


def test_chat_agents_auto_lascia_le_domande_al_rag(monkeypatch):
    _mock_tenant(monkeypatch)
    _enable_bridge(monkeypatch)
    monkeypatch.setattr(settings, "agents_auto", True)
    _mock_rag(monkeypatch)

    def no_call(*a, **k):
        raise AssertionError("una domanda (non task-like) resta al RAG")
    monkeypatch.setattr(agents_bridge, "route", no_call)

    r = client.post("/chat", json={"message": "qual è il fatturato di ATS?"},
                    headers={"X-Tenant-Key": "K"})
    assert r.status_code == 200
    assert r.json()["answer"] == "risposta-rag"


# ── SICUREZZA: lo scope/filtro Qdrant del RAG NON cambia col ponte ────────────
def test_scope_rag_invariato_col_ponte(monkeypatch):
    """Sul path di fallback i grant passati al retrieval restano quelli del tenant,
    identici a prescindere dal ponte agenti."""
    _mock_tenant(monkeypatch)
    _enable_bridge(monkeypatch)
    cap = {}
    _mock_rag(monkeypatch, capture=cap)
    monkeypatch.setattr(agents_bridge, "route", lambda *a, **k: None)   # forza il fallback

    client.post("/chat", json={"message": "scrivi", "agent": True},
                headers={"X-Tenant-Key": "K"})
    assert cap["grants"]["allowed_scopes"] == ["ats"]
    assert "agent" not in cap["grants"] and "tenant" not in cap["grants"]
    assert rag.build_filter(cap["grants"]).should[0].key == "scope"
