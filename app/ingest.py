"""Ingestion del cervello: legge le note .md, calcola i SEGMENTI di permesso
(org/tenant/sotto-tenant), le spezza in chunk, le trasforma in embeddings e le
carica su Qdrant.

I segmenti determinano chi può vedere cosa. La mappatura verso il modello a tre
livelli di OVYON (org > tenant > sotto-tenant) è derivata dal path della nota
(vedi ovyon/docs/doc-ovyon-ember-scope nel cervello):

  path nel vault                | org      | tenant       | sub_tenant
  ------------------------------|----------|--------------|-------------
  forma/clienti/<X>/<sub>/...   | forma    | <X>          | <sub> (se c'è)
  forma/<area>/...              | forma    | forma-core   | <area>
  andrea-aloia/<sub>/...        | personal | andrea       | <sub> (se c'è)
  ovyon/<sub>/...               | ovyon    | ovyon        | <sub> (es. docs)
  (altro)                       | altro    | altro        | —

Il `tenant` coincide con lo storico `scope`: `scope_for()` resta quindi
retro-compatibile (stessi valori di prima) ed è definito come alias del tenant.
Questo permette una re-ingest ADDITIVA (aggiunge org/sub_tenant al payload) senza
rompere i filtri esistenti basati su `allowed_scopes`.
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


def segments_for(rel: Path) -> dict:
    """Ricava i tre segmenti di permesso (org/tenant/sub_tenant) dal path della nota.

    `rel` è il path relativo al vault, filename incluso (es. forma/clienti/ats/x.md):
    le componenti-cartella sono `rel.parts[:-1]`. Il sotto-tenant è la cartella
    intermedia — presente solo quando la nota è annidata sotto il tenant, altrimenti None.
    """
    parts = rel.parts
    if parts and parts[0] == "forma":
        if len(parts) >= 3 and parts[1] == "clienti":
            # forma/clienti/<X>/[<sub>/]file.md → tenant=<X>, sub=<sub> se annidata
            sub = parts[3] if len(parts) >= 5 else None
            return {"org": "forma", "tenant": parts[2], "sub_tenant": sub}
        # forma/<area>/[.../]file.md → tenant=forma-core, sub=<area> se annidata
        sub = parts[1] if len(parts) >= 3 else None
        return {"org": "forma", "tenant": "forma-core", "sub_tenant": sub}
    if parts and parts[0] == "andrea-aloia":
        sub = parts[1] if len(parts) >= 3 else None
        return {"org": "personal", "tenant": "andrea", "sub_tenant": sub}
    if parts and parts[0] == "ovyon":
        sub = parts[1] if len(parts) >= 3 else None
        return {"org": "ovyon", "tenant": "ovyon", "sub_tenant": sub}
    return {"org": "altro", "tenant": "altro", "sub_tenant": None}


def scope_for(rel: Path) -> str:
    """Storico `scope` = livello `tenant`. Mantenuto per retro-compatibilità
    (allowed_scopes, filtri esistenti). Vedi segments_for() per i tre livelli."""
    return segments_for(rel)["tenant"]


# Campi di permesso attesi nel payload Qdrant dopo la re-ingest a tre livelli.
# `sub_tenant` può essere None (nota non annidata): la sua CHIAVE deve comunque esserci.
REQUIRED_PAYLOAD_FIELDS = ("scope", "org", "tenant", "sub_tenant")


def check_payload(payload: dict) -> list[str]:
    """Ritorna i campi di permesso MANCANTI in un payload Qdrant (lista vuota = ok).
    Verifica anche la coerenza scope == tenant (invariante della mappatura)."""
    missing = [f for f in REQUIRED_PAYLOAD_FIELDS if f not in (payload or {})]
    if not missing and payload.get("scope") != payload.get("tenant"):
        missing.append("scope!=tenant")
    return missing


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
    # Indici per i campi di permesso, così Qdrant può filtrare per livello:
    #   scope/tenant (retro-compatibili), org e sub_tenant (nuovi, additivi).
    for field in ("scope", "org", "tenant", "sub_tenant"):
        try:
            c.create_payload_index(
                settings.qdrant_collection,
                field_name=field,
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
        seg = segments_for(rel)
        # `scope` = alias di `tenant`: mantiene intatti i filtri e i dati esistenti.
        scope = seg["tenant"]
        title = meta.get("title", md.stem)
        tags = meta.get("tags", "")
        for ci, ch in enumerate(chunk(body)):
            metas.append({
                "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"{rel}::{ci}")),
                "scope": scope, "org": seg["org"], "tenant": seg["tenant"],
                "sub_tenant": seg["sub_tenant"],
                "slug": md.stem, "title": title,
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
                     ("scope", "org", "tenant", "sub_tenant",
                      "slug", "title", "path", "tags", "chunk", "text")},
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
