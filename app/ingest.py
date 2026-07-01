"""Ingestion del cervello: legge le note .md, calcola lo SCOPE (la chiave-permesso),
le spezza in chunk, le trasforma in embeddings e le carica su Qdrant.

Lo SCOPE determina chi può vedere cosa:
  - forma/clienti/<X>/...  -> scope "<X>"  (es. "ats", "hrh")  ← include i contratti del cliente
  - forma/...              -> "forma-core"
  - andrea-aloia/...       -> "andrea"
  - ovyon/...              -> "ovyon"
"""
import re
import uuid
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, PayloadSchemaType

from .config import settings
from .providers import embed, EMBED_DIM

# Cartelle non utili al chatbot (derivati, scratch, fonti grezze).
# 'contratti' è escluso PER DEFAULT (dati personali): per farli interrogare dal
# consulente, togli "contratti" da questo set quando hai DPA + region Qdrant UE a posto.
SKIP_DIRS = {".git", ".obsidian", "_showcase", "workspace", "sources", "contratti"}


def scope_for(rel: Path) -> str:
    parts = rel.parts
    if parts and parts[0] == "forma":
        if len(parts) >= 3 and parts[1] == "clienti":
            return parts[2]
        return "forma-core"
    if parts and parts[0] == "andrea-aloia":
        return "andrea"
    if parts and parts[0] == "ovyon":
        return "ovyon"
    return "altro"


def chunk(text: str, size: int = 1200, overlap: int = 200) -> list[str]:
    out, i = [], 0
    while i < len(text):
        out.append(text[i:i + size])
        i += size - overlap
    return out


def _parse_note(path: Path):
    """Mini-parser frontmatter YAML (niente dipendenze esterne). Ritorna (meta, body)."""
    text = path.read_text("utf-8")
    meta, body = {}, text
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            fm = text[3:end]
            body = text[end + 4:].lstrip("\n")
            for line in fm.splitlines():
                m = re.match(r"^(\w+):\s*(.*)", line)
                if m:
                    meta[m.group(1)] = m.group(2).strip()
    return meta, body


def client() -> QdrantClient:
    return QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key or None)


def ensure_collection(c: QdrantClient, fresh: bool = False) -> None:
    existing = [col.name for col in c.get_collections().collections]
    if fresh and settings.qdrant_collection in existing:
        # Reindicizzazione pulita: azzera la collection (rimuove duplicati e
        # note cancellate/rinominate) e la ricrea da zero.
        c.delete_collection(settings.qdrant_collection)
        existing = [col.name for col in c.get_collections().collections]
    if settings.qdrant_collection not in existing:
        c.create_collection(
            settings.qdrant_collection,
            vectors_config=VectorParams(size=EMBED_DIM, distance=Distance.COSINE),
        )
    # Indice sul campo 'scope': serve a Qdrant per filtrare per settore/tenant.
    try:
        c.create_payload_index(
            settings.qdrant_collection,
            field_name="scope",
            field_schema=PayloadSchemaType.KEYWORD,
        )
    except Exception:
        pass  # già esistente: ok


def iter_notes(vault: Path):
    for md in sorted(vault.rglob("*.md")):
        rel = md.relative_to(vault)
        if any(p in SKIP_DIRS or p.startswith(".") for p in rel.parts):
            continue
        if md.stem == "_index":
            continue
        yield md, rel


def run() -> dict:
    if not settings.vault_path:
        raise RuntimeError("VAULT_PATH non impostato nel .env")
    vault = Path(settings.vault_path)
    c = client()

    # 1) Raccogli TUTTI i chunk + metadati (nessuna chiamata di rete qui).
    metas: list[dict] = []
    texts: list[str] = []
    n_notes = 0
    for md, rel in iter_notes(vault):
        meta, body = _parse_note(md)
        body = body.strip()
        if not body:
            continue
        n_notes += 1
        scope = scope_for(rel)
        title = meta.get("title", md.stem)
        tags = meta.get("tags", "")
        for ci, ch in enumerate(chunk(body)):
            metas.append({
                "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"{rel}::{ci}")),
                "scope": scope, "slug": md.stem, "title": title,
                "path": str(rel), "tags": tags, "chunk": ci, "text": ch,
            })
            texts.append(ch)

    # 2) Embedding in BATCH: poche richieste invece di una per nota → molto meno
    #    rate-limit. Se Mistral risponde 429, embed() ritenta da solo (backoff).
    #    Finché questo non riesce, la collection esistente resta INTATTA.
    vectors: list[list[float]] = []
    batch = 64
    for i in range(0, len(texts), batch):
        vectors.extend(embed(texts[i:i + batch]))

    points = [
        PointStruct(
            id=m["id"], vector=v,
            payload={k: m[k] for k in
                     ("scope", "slug", "title", "path", "tags", "chunk", "text")},
        )
        for m, v in zip(metas, vectors)
    ]

    # 3) Solo ORA che tutti gli embedding sono pronti azzeriamo, ricreiamo e
    #    carichiamo: la riconversione è di fatto atomica (nessun cervello vuoto).
    ensure_collection(c, fresh=True)
    if points:
        c.upsert(settings.qdrant_collection, points=points, wait=True)
    return {"notes": n_notes, "chunks": len(points)}


if __name__ == "__main__":
    print(run())
