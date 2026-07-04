"""Test del retrieval strutturato (ovy_search/get_document/list_context):
riassemblaggio chunk, metadati hit e contesto grant. Puri, senza rete."""
from app import rag as R
from app import ingest as I


class _Hit:
    def __init__(self, payload):
        self.payload = payload


def test_reassemble_toglie_overlap():
    # Simula ingest.chunk() con overlap 200 su un corpo noto.
    body = "".join(chr(65 + (i % 26)) for i in range(3000))  # 3000 caratteri deterministici
    chunks = I.chunk(body, size=1200, overlap=200)
    assert len(chunks) > 1
    assert R._reassemble(chunks, overlap=200) == body


def test_reassemble_singolo_chunk():
    assert R._reassemble(["ciao"], overlap=200) == "ciao"
    assert R._reassemble([]) == ""


def test_hit_meta_usa_tenant_o_scope():
    h = _Hit({"slug": "doc-x", "title": "Doc X", "org": "forma", "tenant": "ats",
              "sub_tenant": "progetti", "path": "forma/clienti/ats/x.md",
              "text": "y" * 500})
    m = R._hit_meta(h)
    assert m["slug"] == "doc-x" and m["tenant"] == "ats" and m["org"] == "forma"
    assert len(m["snippet"]) == 300  # troncato

    # retro-compat: payload storico senza `tenant`, solo `scope`
    h2 = _Hit({"slug": "s", "scope": "ats", "text": "z"})
    assert R._hit_meta(h2)["tenant"] == "ats"


def test_list_context():
    ctx = R.list_context({"allowed_scopes": ["ats"], "allowed_orgs": ["forma"]})
    assert ctx["allowed_tenants"] == ["ats"]
    assert ctx["allowed_orgs"] == ["forma"]
    assert ctx["master"] is False

    assert R.list_context(["*"])["master"] is True
    assert R.list_context(["ats"])["allowed_tenants"] == ["ats"]
