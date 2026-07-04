"""Test della costruzione del filtro grant (org/tenant/sub_tenant) e della
normalizzazione dei grant. Puri, senza rete (nessuna query a Qdrant)."""
from app import rag as R


def _keys(flt):
    """Estrae le coppie (field, valori) dalle condizioni `should` di un Filter."""
    return {c.key: list(c.match.any) for c in (flt.should or [])}


def test_legacy_lista_e_livello_tenant():
    """Una lista storica = allowed_scopes, filtro sul campo `scope`."""
    flt = R.build_filter(["ats", "hrh"])
    assert flt.must is None
    assert _keys(flt) == {"scope": ["ats", "hrh"]}


def test_master_lista_nessun_filtro():
    assert R.build_filter(["*"]) is None


def test_master_dict_nessun_filtro():
    assert R.build_filter({"allowed_orgs": ["*"]}) is None


def test_dict_tre_livelli():
    flt = R.build_filter({
        "allowed_scopes": ["ats"],
        "allowed_orgs": ["forma"],
        "allowed_sub_tenants": ["docs"],
    })
    assert _keys(flt) == {"scope": ["ats"], "org": ["forma"], "sub_tenant": ["docs"]}


def test_dict_solo_org():
    flt = R.build_filter({"allowed_orgs": ["forma"]})
    assert _keys(flt) == {"org": ["forma"]}


def test_allowed_tenants_alias():
    """`allowed_tenants` è accettato come sinonimo di `allowed_scopes`."""
    flt = R.build_filter({"allowed_tenants": ["ats"]})
    assert _keys(flt) == {"scope": ["ats"]}


def test_vuoto_nega_tutto():
    """Nessun grant → filtro impossibile (deny-by-default), come lo storico."""
    for grants in ([], {}, {"allowed_scopes": []}):
        flt = R.build_filter(grants)
        assert flt.should is None
        assert flt.must and flt.must[0].key == "scope"
        assert list(flt.must[0].match.any) == ["__none__"]


def test_scopes_of():
    assert R.scopes_of(["ats"]) == ["ats"]
    assert R.scopes_of({"allowed_scopes": ["a", "b"]}) == ["a", "b"]
    assert R.scopes_of({"allowed_tenants": ["c"]}) == ["c"]
    assert R.scopes_of({"allowed_orgs": ["forma"]}) == []
