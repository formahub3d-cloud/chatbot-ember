"""P0-bis (sintesi architettura 29-07) — perimetro corretto dopo verifica:

- parte 2: GUARD anti-svuotamento — un vault vuoto/mancante NON azzera mai la
  collection Qdrant esistente (prima: delete+recreate senza soglia, in silenzio);
- parte 3: perimetro del cervello — workspace/ e sources/ DENTRO (runbook),
  _templates/_bozze/contratti/chatbot-jarvis FUORI (contratti non negoziabile);
- parte 4: [[wikilink]] estratti dal testo COMPLETO (frontmatter incluso),
  risolti agli slug reali (rotti e auto-riferimenti scartati) e scritti nel
  campo `links` di OGNI frammento; conteggio archi allineato al generatore
  del vault (stessa regex, stesso insieme di note).

La parte 1 del prompt originale (vault da git) esisteva già: sync_vault +
VAULT_GIT_URL/TOKEN, con redazione del token nei log (test in test_reingest)."""
import pytest

from app import brain, ingest
from app.config import settings


def _vault(tmp_path, files: dict):
    for rel, text in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return tmp_path


class FakeQdrant:
    """Registra le chiamate distruttive: il guard si giudica da qui."""
    def __init__(self):
        self.deleted = []
        self.created = []
        self.upserts = []

    def get_collections(self):
        from types import SimpleNamespace
        return SimpleNamespace(collections=[SimpleNamespace(name="cervello")])

    def delete_collection(self, name):
        self.deleted.append(name)

    def create_collection(self, name, **kw):
        self.created.append(name)

    def create_payload_index(self, *a, **kw):
        pass

    def upsert(self, name, points=None, wait=True):
        self.upserts.append(len(points or []))


# ── parte 2: guard anti-svuotamento ───────────────────────────────────────────
def test_guard_vault_vuoto_non_tocca_la_collection(tmp_path, monkeypatch):
    fake = FakeQdrant()
    monkeypatch.setattr(settings, "vault_path", str(tmp_path))   # vault VUOTO
    monkeypatch.setattr(settings, "vault_git_url", "")
    monkeypatch.setattr(ingest, "client", lambda: fake)
    monkeypatch.setattr(ingest, "embed", lambda texts: [[0.0] * 8 for _ in texts])
    with pytest.raises(RuntimeError, match="ingest annullato"):
        ingest.run()
    # la collection PRECEDENTE è intatta: né cancellata né ricreata né scritta
    assert fake.deleted == [] and fake.created == [] and fake.upserts == []


def test_guard_soglia_configurabile(tmp_path, monkeypatch):
    _vault(tmp_path, {"forma/a.md": "contenuto", "forma/b.md": "contenuto"})
    fake = FakeQdrant()
    monkeypatch.setattr(settings, "vault_path", str(tmp_path))
    monkeypatch.setattr(settings, "vault_git_url", "")
    monkeypatch.setattr(settings, "ingest_min_notes", 2)         # soglia = note trovate
    monkeypatch.setattr(ingest, "client", lambda: fake)
    monkeypatch.setattr(ingest, "embed", lambda texts: [[0.0] * 8 for _ in texts])
    out = ingest.run()                                           # a soglia: passa
    assert out["notes"] == 2 and fake.upserts


# ── parte 3: perimetro (una lista sola) ───────────────────────────────────────
def test_perimetro_workspace_dentro_contratti_fuori(tmp_path):
    _vault(tmp_path, {
        "forma/nota.md": "x", "workspace/runbook.md": "x", "sources/fonte.md": "x",
        "_templates/t.md": "x", "_bozze/b.md": "x", "contratti/c.md": "x",
        "chatbot-jarvis/legacy.md": "x", "_showcase/s.md": "x",
    })
    inclusi = {str(rel) for _, rel in ingest.iter_notes(tmp_path)}
    assert "forma/nota.md" in inclusi
    assert "workspace/runbook.md" in inclusi          # i runbook si interrogano
    assert "sources/fonte.md" in inclusi
    for fuori in ("_templates/t.md", "_bozze/b.md", "contratti/c.md",
                  "chatbot-jarvis/legacy.md", "_showcase/s.md"):
        assert fuori not in inclusi


# ── parte 4: link dal testo completo, risolti, nel payload ────────────────────
def test_wikilink_da_frontmatter_corpo_alias_ancora():
    raw = ("---\ntitle: Nota\nlinks:\n  - [[alfa]]\n  - [[beta|etichetta]]\n---\n"
           "Nel corpo cito [[gamma#sezione]] e di nuovo [[alfa]] e [[rotta-inesistente]].")
    assert ingest.wikilink_targets(raw) == ["alfa", "beta", "gamma", "rotta-inesistente"]


def test_links_risolti_nel_payload_di_ogni_frammento(tmp_path, monkeypatch):
    _vault(tmp_path, {
        "forma/alfa.md": "---\nlinks:\n  - [[beta]]\n---\n" + "testo " * 400,
        "forma/beta.md": "cito [[alfa]] e [[fantasma]] e me stessa [[beta]]",
        "forma/gamma.md": "nessun collegamento qui",
    })
    fake = FakeQdrant()
    captured = {}

    def fake_upsert(name, points=None, wait=True):
        captured["points"] = points
    fake.upsert = fake_upsert
    monkeypatch.setattr(settings, "vault_path", str(tmp_path))
    monkeypatch.setattr(settings, "vault_git_url", "")
    monkeypatch.setattr(settings, "ingest_min_notes", 1)
    monkeypatch.setattr(ingest, "client", lambda: fake)
    monkeypatch.setattr(ingest, "embed", lambda texts: [[0.0] * 8 for _ in texts])
    out = ingest.run()
    by_slug = {}
    for p in captured["points"]:
        by_slug.setdefault(p.payload["slug"], []).append(p.payload)
    # frontmatter contato; rotti e auto-riferimenti scartati; su OGNI frammento
    assert all(pl["links"] == ["beta"] for pl in by_slug["alfa"])
    assert len(by_slug["alfa"]) > 1                    # nota lunga → più frammenti
    assert all(pl["links"] == ["alfa"] for pl in by_slug["beta"])
    assert all(pl["links"] == [] for pl in by_slug["gamma"])
    # validazione payload aggiornata: `links` è un campo richiesto
    assert ingest.check_payload(captured["points"][0].payload) == []
    assert "links" in ingest.check_payload({"scope": "x", "org": "x",
                                            "tenant": "x", "sub_tenant": "x"})
    assert out["graph_links"] == 1                     # alfa↔beta: UN arco non orientato


def test_conteggio_archi_allineato_al_generatore_del_vault():
    """Stessa regex del build.py del vault (LINK_RE): sullo stesso insieme di
    note i due conteggi DEVONO coincidere — frontmatter incluso."""
    import re
    vault_link_re = re.compile(r"\[\[([^\]|#\n]+?)(?:[|#][^\]\n]*)?\]\]")   # build.py
    notes = {
        "a": "---\nlinks:\n  - [[b]]\n---\ncorpo con [[c|alias]]",
        "b": "cito [[a#sez]] e [[a]]",
        "c": "solo и testo",
    }
    # archi non orientati, deduplicati, risolti sull'insieme {a,b,c}
    def edges(texts, link_re):
        out = set()
        for src, t in texts.items():
            for m in link_re.finditer(t):
                dst = m.group(1).strip().lower()
                if dst in texts and dst != src:
                    out.add((min(src, dst), max(src, dst)))
        return out
    nostro = edges(notes, ingest._LINK_RE)
    vault = edges(notes, vault_link_re)
    assert nostro == vault == {("a", "b"), ("a", "c")}
    # e il grafo del pannello (brain) conta uguale, leggendo il testo completo
    g = brain.build_graph([{"slug": s, "title": s, "tenant": "forma-core", "raw": t}
                           for s, t in notes.items()])
    assert len(g["links"]) == 2
