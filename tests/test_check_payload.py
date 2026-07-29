"""Test del controllo payload post-ingest (tre livelli + invariante scope==tenant
+ campo `links` delle sinapsi, P0-bis parte 4)."""
from app import ingest as I


def test_payload_completo_ok():
    pl = {"scope": "ats", "org": "forma", "tenant": "ats", "sub_tenant": None, "links": []}
    assert I.check_payload(pl) == []


def test_sub_tenant_none_ammesso():
    # sub_tenant None è valido: conta la presenza della CHIAVE, non il valore
    pl = {"scope": "ovyon", "org": "ovyon", "tenant": "ovyon", "sub_tenant": None, "links": []}
    assert I.check_payload(pl) == []


def test_campi_mancanti():
    # payload "storico" senza org/tenant/sub_tenant
    assert set(I.check_payload({"scope": "ats"})) == {"org", "tenant", "sub_tenant", "links"}


def test_incoerenza_scope_tenant():
    pl = {"scope": "ats", "org": "forma", "tenant": "forma-core", "sub_tenant": None, "links": []}
    assert "scope!=tenant" in I.check_payload(pl)


def test_payload_vuoto():
    assert set(I.check_payload({})) == {"scope", "org", "tenant", "sub_tenant", "links"}
