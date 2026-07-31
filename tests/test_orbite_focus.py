"""O2 «Lavora con Divina» — il focus (l'orbita scelta) RESTRINGE soltanto.

Il clic su un'orbita in console manda ChatIn.focus = {label, slugs}: il filtro
Qdrant aggiunge le slug in `must`, in AND coi grant del tenant. Può ridurre ciò
che si vede, MAI allargarlo: la sicurezza resta server-side, come per lo scope.
"""
from fastapi.testclient import TestClient

from app import main, rag, tenants, security
from app.config import settings

client = TestClient(main.app)


# ── build_filter: il focus è un AND, mai un allargamento ─────────────────────
def test_focus_su_master_filtra_le_slug():
    f = rag.build_filter("*", focus_slugs=["cliente-ats", "scheda-ats"])
    assert f is not None                       # il master senza focus era None
    cond = f.must[0]
    assert cond.key == "slug"
    assert set(cond.match.any) == {"cliente-ats", "scheda-ats"}


def test_focus_su_tenant_va_in_AND_coi_grant():
    f = rag.build_filter({"allowed_scopes": ["ats"]}, focus_slugs=["cliente-ats"])
    # must = [slug ∈ orbita, Filter(should=grant)] — AND esplicito annidato
    keys = [getattr(c, "key", None) for c in f.must]
    assert "slug" in keys
    nested = [c for c in f.must if getattr(c, "should", None)]
    assert nested and nested[0].should[0].key == "scope"
    assert nested[0].should[0].match.any == ["ats"]


def test_senza_focus_il_filtro_resta_identico():
    assert rag.build_filter("*") is None
    f = rag.build_filter({"allowed_scopes": ["ats"]})
    assert f.must is None or not f.must
    assert f.should[0].key == "scope"


def test_focus_non_scavalca_grant_vuoti():
    """Tenant senza grant validi: nega tutto ANCHE con un focus pieno."""
    f = rag.build_filter({"allowed_scopes": []}, focus_slugs=["cliente-ats"])
    assert f.must[0].key == "scope"
    assert f.must[0].match.any == ["__none__"]


# ── _focus_slugs: validazione dell'input dal client ──────────────────────────
class _B:
    def __init__(self, focus):
        self.focus = focus


def test_focus_slugs_normalizza_e_scarta_il_rumore():
    out = main._focus_slugs(_B({"label": "ATS", "slugs": [" Cliente-ATS ", "", None, 42, "scheda-ats"]}))
    assert out == ["cliente-ats", "42", "scheda-ats"]


def test_focus_slugs_cap_300_e_none():
    assert main._focus_slugs(_B(None)) is None
    assert main._focus_slugs(_B({"slugs": []})) is None
    assert main._focus_slugs(_B("non-un-dict")) is None
    out = main._focus_slugs(_B({"slugs": [f"n{i}" for i in range(500)]}))
    assert len(out) == 300


# ── /chat: il focus arriva a rag.answer, i grant restano quelli del tenant ───
def test_chat_passa_il_focus_e_non_tocca_i_grant(monkeypatch):
    seen = {}
    monkeypatch.setattr(tenants, "get_tenant_by_key",
                        lambda k: {"name": "X", "allowed_origins": [], "allowed_scopes": ["ats"]})
    monkeypatch.setattr(security, "origin_allowed", lambda o, a: True)
    monkeypatch.setattr(main, "rate_ok", lambda k: True)

    def fake_answer(q, grants, **kw):
        seen["grants"] = grants
        seen["focus"] = kw.get("focus_slugs")
        seen["free"] = kw.get("free")
        return {"answer": "ok", "sources": [], "scopes": ["ats"]}
    monkeypatch.setattr(rag, "answer", fake_answer)
    r = client.post("/chat", json={"message": "ciao",
                                   "focus": {"label": "ATS", "slugs": ["cliente-ats"]}},
                    headers={"X-Tenant-Key": "K"})
    assert r.status_code == 200
    assert seen["focus"] == ["cliente-ats"]
    g = seen["grants"]                          # i grant sono SOLO quelli del tenant
    assert (g.get("allowed_scopes") or g.get("allowed_tenants")) == ["ats"]
    assert "focus" not in g                     # il focus NON entra nei grant
    assert seen["free"] is False               # tenant normale: mai conversazione libera
