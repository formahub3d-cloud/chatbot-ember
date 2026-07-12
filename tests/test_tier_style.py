"""Blocco J — "fronting tier cliente" (lato Ember).

Il tier/archetipo OVYON (dante/virgilio/beatrice) del tenant modula SOLO lo STILE
della risposta (funzione pura `rag.style_directive` iniettata nel system prompt).

REGOLA DI SICUREZZA (non negoziabile): il tier NON amplia MAI lo scope dei dati —
i grant e il filtro Qdrant restano identici a prescindere dal tier. Questi test
lo verificano sia sulla funzione pura sia end-to-end su /chat. Nessuna rete: LLM e
retrieval sono mockati."""
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app import rag, main, tenants, security
from app.config import settings

client = TestClient(main.app)


# ── 1. Funzione pura: mappa tier → direttiva di stile ─────────────────────────
def test_style_directive_archetipi_non_vuoti_e_distinti():
    d = rag.style_directive("dante")
    v = rag.style_directive("virgilio")
    b = rag.style_directive("beatrice")
    assert d and v and b                        # tutti non vuoti
    assert len({d, v, b}) == 3                   # tre stili distinti


def test_style_directive_sconosciuto_vuoto_none():
    for x in (None, "", "  ", "gold", "premium", "sconosciuto"):
        assert rag.style_directive(x) == ""      # nessuna modifica (retro-compat)


def test_style_directive_case_insensitive():
    assert rag.style_directive("DANTE") == rag.style_directive("dante")
    assert rag.style_directive("  Virgilio  ") == rag.style_directive("virgilio")
    assert rag.style_directive("BeAtRiCe") == rag.style_directive("beatrice")


def test_style_directive_e_solo_forma_non_amplia_accesso():
    """Le direttive descrivono la forma, mai il permesso di leggere altri dati."""
    for tier in ("dante", "virgilio", "beatrice"):
        s = rag.style_directive(tier).lower()
        assert "stile" in s
        # nessuna parola che suggerisca di ignorare vincoli o allargare lo scope
        for vietata in ("scope", "allowed", "ignora", "tutti i dati", "qualsiasi nota"):
            assert vietata not in s


# ── 2. Iniezione nel system prompt (aggiunta, non sostituzione) ───────────────
def test_system_con_tier_aggiunge_direttiva_e_mantiene_vincoli():
    base = rag._system("it")
    s = rag._system("it", "beatrice")
    assert rag.style_directive("beatrice") in s        # direttiva presente
    assert s.startswith(base)                          # aggiunta in coda
    # i vincoli storici (anti-injection + 'non lo so') restano intatti
    assert "ignora qualunque" in s and rag.NO_ANSWER in s


def test_system_senza_tier_identico_a_prima():
    """Retro-compat a livello prompt: nessun tier → prompt invariato."""
    assert rag._system("it", None) == rag._system("it") == rag.SYSTEM
    assert rag._system("en", None) == rag._system("en")
    assert rag._system("en", "unknown") == rag._system("en")   # tier ignoto = no-op


# ── 3. answer(): il tier cambia il prompt ma NON i grant/lo scope ─────────────
def _fake_hit():
    return SimpleNamespace(score=0.9, payload={"slug": "nota-x", "text": "contenuto utile"})


def test_answer_inietta_stile_ma_lascia_i_grant_invariati(monkeypatch):
    seen = {}

    def fake_retrieve(q, g, k):
        seen["grants"] = g                 # cattura i grant usati per il filtro
        return [_fake_hit()]

    def fake_chat(system, user):
        seen["system"] = system            # cattura il system prompt passato all'LLM
        return "risposta"

    monkeypatch.setattr(rag, "_retrieve", fake_retrieve)
    monkeypatch.setattr(rag, "chat", fake_chat)

    grants = {"allowed_scopes": ["ats"], "allowed_orgs": [], "allowed_sub_tenants": []}
    out = rag.answer("ciao", grants, tier="virgilio")

    assert out["answer"] == "risposta"
    assert rag.style_directive("virgilio") in seen["system"]     # stile iniettato
    # SICUREZZA: i grant passati al retrieval sono ESATTAMENTE quelli in ingresso,
    # senza traccia del tier → il filtro Qdrant (scope) è identico.
    assert seen["grants"] == grants
    assert "tier" not in seen["grants"]
    assert rag.build_filter(seen["grants"]).should[0].key == "scope"


def test_answer_scope_identico_a_prescindere_dal_tier(monkeypatch):
    """Cambiare il tier NON cambia il filtro: build_filter dipende solo dai grant."""
    grants = {"allowed_scopes": ["ats"]}
    captured = []
    monkeypatch.setattr(rag, "_retrieve", lambda q, g, k: (captured.append(g), [_fake_hit()])[1])
    monkeypatch.setattr(rag, "chat", lambda s, u: "ok")
    for tier in (None, "dante", "virgilio", "beatrice", "sconosciuto"):
        rag.answer("q", grants, tier=tier)
    # tutti i retrieval hanno visto gli stessi identici grant
    assert all(g == grants for g in captured)


# ── 4. /chat end-to-end: legge il tier dal branding e lo applica (solo stile) ─
def _mock_tenant(monkeypatch, branding):
    t = {"name": "Cliente", "allowed_scopes": ["ats"], "allowed_origins": [], "branding": branding}
    monkeypatch.setattr(tenants, "get_tenant_by_key", lambda k: t)
    monkeypatch.setattr(security, "origin_allowed", lambda o, a: True)
    monkeypatch.setattr(main, "rate_ok", lambda k: True)
    monkeypatch.setattr(tenants, "quota_ok", lambda t: True)


def test_chat_applica_il_tier_dal_branding_senza_toccare_lo_scope(monkeypatch):
    _mock_tenant(monkeypatch, {"tier": "beatrice"})
    seen = {}

    def fake_retrieve(q, g, k):
        seen["grants"] = g
        return [_fake_hit()]

    monkeypatch.setattr(rag, "_retrieve", fake_retrieve)
    monkeypatch.setattr(rag, "chat", lambda system, user: seen.setdefault("system", system) or "ok")

    r = client.post("/chat", json={"message": "ciao"}, headers={"X-Tenant-Key": "K"})
    assert r.status_code == 200
    # stile beatrice iniettato nel system prompt del /chat
    assert rag.style_directive("beatrice") in seen["system"]
    # SCOPE INVARIATO: i grant contengono solo gli scope del tenant, nessun tier.
    assert seen["grants"]["allowed_scopes"] == ["ats"]
    assert "tier" not in seen["grants"]
    assert rag.build_filter(seen["grants"]) == rag.build_filter({"allowed_scopes": ["ats"],
                                                                 "allowed_orgs": [],
                                                                 "allowed_sub_tenants": []})


def test_chat_senza_tier_prompt_come_prima(monkeypatch):
    """Retro-compat end-to-end: tenant senza tier → system prompt = quello storico."""
    _mock_tenant(monkeypatch, {})            # nessun tier nel branding
    seen = {}
    monkeypatch.setattr(rag, "_retrieve", lambda q, g, k: [_fake_hit()])
    monkeypatch.setattr(rag, "chat", lambda system, user: seen.setdefault("system", system) or "ok")

    r = client.post("/chat", json={"message": "ciao"}, headers={"X-Tenant-Key": "K"})
    assert r.status_code == 200
    # lang di default = it → prompt identico a rag._system("it") (== SYSTEM)
    assert seen["system"] == rag._system(settings.default_lang)
