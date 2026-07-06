"""N1 · Isolamento cross-tenant: un tenant non deve MAI vedere i dati di un altro.

Verifica la semantica del filtro Qdrant prodotto da rag.build_filter valutandolo
in memoria contro payload realistici (org/tenant/sub_tenant come li scrive
ingest.segments_for). È il cuore della promessa di prodotto: il bot ATS non
risponde su FORMA/HRH e viceversa, e il filtro è imposto lato server.
"""
from qdrant_client.models import Filter, FieldCondition, MatchAny, MatchValue

from app import rag


# ── Valutatore minimale del Filter Qdrant (should/must/must_not + Match) ──────────
def _cond_ok(cond, payload) -> bool:
    if isinstance(cond, Filter):
        return _filter_ok(cond, payload)
    val = payload.get(cond.key)
    m = cond.match
    if isinstance(m, MatchAny):
        return val in list(m.any)
    if isinstance(m, MatchValue):
        return val == m.value
    return False


def _filter_ok(flt, payload) -> bool:
    if flt is None:          # None = master: nessun vincolo, vede tutto
        return True
    if getattr(flt, "must", None) and not all(_cond_ok(c, payload) for c in flt.must):
        return False
    if getattr(flt, "should", None) and not any(_cond_ok(c, payload) for c in flt.should):
        return False
    if getattr(flt, "must_not", None) and any(_cond_ok(c, payload) for c in flt.must_not):
        return False
    return True


# Payload d'esempio come li produce l'ingest (scope == tenant).
ATS = {"scope": "ats", "tenant": "ats", "org": "forma", "sub_tenant": None}
HRH = {"scope": "hrh", "tenant": "hrh", "org": "forma", "sub_tenant": None}
FORMA_CORE = {"scope": "forma-core", "tenant": "forma-core", "org": "forma",
              "sub_tenant": "area-sviluppo-web"}
PERSONAL = {"scope": "andrea", "tenant": "andrea", "org": "personal", "sub_tenant": None}
ALL = [ATS, HRH, FORMA_CORE, PERSONAL]


def _visible(grants):
    flt = rag.build_filter(grants)
    return [p["scope"] for p in ALL if _filter_ok(flt, p)]


def test_ats_vede_solo_ats():
    assert _visible({"allowed_scopes": ["ats"]}) == ["ats"]


def test_hrh_vede_solo_hrh():
    assert _visible({"allowed_scopes": ["hrh"]}) == ["hrh"]


def test_ats_non_vede_hrh_ne_forma():
    vis = _visible({"allowed_scopes": ["ats"]})
    assert "hrh" not in vis and "forma-core" not in vis and "andrea" not in vis


def test_grant_org_copre_tutti_i_tenant_della_org():
    # Una chiave a livello org 'forma' vede tutti i tenant forma, MA non il personale.
    vis = _visible({"allowed_orgs": ["forma"]})
    assert set(vis) == {"ats", "hrh", "forma-core"} and "andrea" not in vis


def test_master_vede_tutto():
    assert set(_visible({"allowed_scopes": ["*"]})) == {"ats", "hrh", "forma-core", "andrea"}


def test_grant_vuoto_nega_tutto():
    # Nessuno scope concesso = deny-all (nessuna fuga di dati per default).
    assert _visible({"allowed_scopes": []}) == []


def test_lista_storica_equivalente_al_dict():
    # Retro-compatibilità: la lista storica ['ats'] filtra come {'allowed_scopes':['ats']}.
    assert _visible(["ats"]) == _visible({"allowed_scopes": ["ats"]})
