"""Test della derivazione dei segmenti di permesso dal path (org/tenant/sub_tenant)
e della retro-compatibilità di scope_for. Puri, senza rete."""
from pathlib import Path

from app import ingest as I


def test_segments_forma_cliente_senza_sottocartella():
    seg = I.segments_for(Path("forma/clienti/ats/contratto.md"))
    assert seg == {"org": "forma", "tenant": "ats", "sub_tenant": None}


def test_segments_forma_cliente_con_sottocartella():
    seg = I.segments_for(Path("forma/clienti/ats/progetti/sito.md"))
    assert seg == {"org": "forma", "tenant": "ats", "sub_tenant": "progetti"}


def test_segments_forma_core_con_area():
    seg = I.segments_for(Path("forma/docs/doc-stack-tecnico.md"))
    assert seg == {"org": "forma", "tenant": "forma-core", "sub_tenant": "docs"}


def test_segments_forma_core_file_radice():
    seg = I.segments_for(Path("forma/nota.md"))
    assert seg == {"org": "forma", "tenant": "forma-core", "sub_tenant": None}


def test_segments_andrea():
    assert I.segments_for(Path("andrea-aloia/self.md")) == {
        "org": "personal", "tenant": "andrea", "sub_tenant": None}
    assert I.segments_for(Path("andrea-aloia/note/x.md"))["sub_tenant"] == "note"


def test_segments_ovyon():
    assert I.segments_for(Path("ovyon/self-ovyon.md")) == {
        "org": "ovyon", "tenant": "ovyon", "sub_tenant": None}
    assert I.segments_for(Path("ovyon/docs/doc-ovyon-ember-scope.md")) == {
        "org": "ovyon", "tenant": "ovyon", "sub_tenant": "docs"}


def test_segments_altro():
    assert I.segments_for(Path("qualcosa/x.md")) == {
        "org": "altro", "tenant": "altro", "sub_tenant": None}


def test_scope_for_retrocompatibile():
    """scope_for deve restituire ESATTAMENTE i valori storici (= tenant)."""
    casi = {
        "forma/clienti/ats/x.md": "ats",
        "forma/clienti/hrh/y.md": "hrh",
        "forma/docs/z.md": "forma-core",
        "forma/w.md": "forma-core",
        "andrea-aloia/a.md": "andrea",
        "ovyon/o.md": "ovyon",
        "boh/b.md": "altro",
    }
    for p, atteso in casi.items():
        assert I.scope_for(Path(p)) == atteso
        assert I.scope_for(Path(p)) == I.segments_for(Path(p))["tenant"]
