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
import logging
import re
import subprocess
import uuid
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.models import (Distance, VectorParams, PointStruct, PayloadSchemaType,
                                  Filter, FieldCondition, MatchValue)

from .config import settings
from .providers import embed, EMBED_DIM

log = logging.getLogger("ember.ingest")


# ── Auto-ingest: aggiornamento del vault da git prima di indicizzare ──────────
# Su Railway il vault (cartella VAULT_PATH) non si aggiorna da solo: se VAULT_GIT_URL
# è impostato, prima di leggere le note si prendono quelle fresche dal repo del cervello.
# Isolato in una funzione pura/testabile, separata dall'esecuzione dell'ingest.

def _redact_url(text: str) -> str:
    """Redige eventuali credenziali (`//utente:token@host`) da un URL o da un
    messaggio d'errore, così il token non finisce MAI nei log (git a volte riecheggia
    l'URL remoto — token incluso — nei messaggi d'errore)."""
    return re.sub(r"//[^/@\s]+@", "//***@", text or "")


def _authed_url(url: str, token: str) -> str:
    """Inietta il token per repo privato: `https://x-access-token:<token>@github.com/...`.
    Token vuoto o schema non-https → URL invariato (repo pubblico / ssh non gestito qui).
    Il risultato NON va mai loggato (contiene il segreto): usare _redact_url() sui log."""
    if token and url.startswith("https://"):
        return f"https://x-access-token:{token}@{url[len('https://'):]}"
    return url


def sync_vault(vault_path: str, url: str, token: str = "") -> bool:
    """Aggiorna il vault locale dal repo git PRIMA dell'ingest. Funzione pura/testabile.

    - `url` vuoto → no-op, ritorna False (comportamento storico: legge la cartella locale).
    - `<vault_path>/.git` esiste → `git -C <vault_path> pull --ff-only`.
    - altrimenti → `git clone --depth 1 <url> <vault_path>`.

    Usa subprocess con LISTA di argomenti (mai shell=True). Il token per repo privato è
    iniettato nell'URL (x-access-token) e non viene MAI loggato: nei log compare solo
    l'URL redatto (host/path senza credenziali). Ritorna True se ha tentato un pull/clone.

    GESTIONE ERRORI (scelta motivata):
    - pull fallito ma esiste già una copia locale (.git) → si LOGGA e si PROSEGUE con la
      copia esistente: meglio indicizzare note leggermente stantie che far esplodere
      l'ingest per un blip di rete. La rete di sicurezza notturna riproverà.
    - clone iniziale fallito → NON c'è alcuna copia locale da cui partire: si solleva
      RuntimeError (→ /ingest risponde 500 con messaggio chiaro), perché senza vault non
      c'è nulla da indicizzare e proseguire indicizzerebbe il vuoto azzerando il cervello.
    """
    if not url:
        return False
    vp = Path(vault_path)
    safe = _redact_url(url)
    if (vp / ".git").exists():
        try:
            subprocess.run(["git", "-C", str(vp), "pull", "--ff-only"],
                           check=True, capture_output=True, text=True)
            log.info("vault: git pull --ff-only ok (%s)", safe)
        except (subprocess.CalledProcessError, OSError) as e:
            # copia locale già presente: si prosegue con quella (non blocchiamo l'ingest).
            log.warning("vault: git pull fallito (%s), proseguo con la copia locale: %s",
                        safe, _redact_url(str(e)))
        return True
    vp.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(["git", "clone", "--depth", "1", _authed_url(url, token), str(vp)],
                       check=True, capture_output=True, text=True)
        log.info("vault: git clone --depth 1 ok (%s → %s)", safe, vp)
    except (subprocess.CalledProcessError, OSError) as e:
        # nessuna copia locale da cui ripartire: senza vault non c'è ingest → errore chiaro.
        log.error("vault: git clone fallito (%s): %s", safe, _redact_url(str(e)))
        raise RuntimeError(f"Impossibile clonare il vault da {safe}") from e
    return True


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
    #   scope/tenant (retro-compatibili), org e sub_tenant (nuovi, additivi),
    #   slug (serve a /document, che filtra la nota per slug con scroll).
    for field in ("scope", "org", "tenant", "sub_tenant", "slug"):
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
    # Auto-ingest: se VAULT_GIT_URL è impostato, aggiorna il vault dal repo del cervello
    # PRIMA di leggerlo. Vuoto = no-op → legge la cartella locale (comportamento storico).
    sync_vault(settings.vault_path, settings.vault_git_url, settings.vault_git_token)
    vault = Path(settings.vault_path)
    c = client()

    # 1) Raccogli TUTTI i chunk + metadati (nessuna chiamata di rete qui).
    metas: list[dict] = []
    texts: list[str] = []
    notes_meta: list[dict] = []   # una voce per NOTA (per il sync metadati su Supabase)
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
        notes_meta.append({
            "org": seg["org"], "tenant": seg["tenant"], "sub_tenant": seg["sub_tenant"],
            "slug": md.stem, "title": title, "path": str(rel), "tags": tags,
            "content": body,   # per la cifratura a riposo su Supabase (content_encrypted)
        })
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

    # 4) Sync METADATI su Supabase (best-effort): popola `documents` per la RLS a
    #    livello di documento. Non deve mai far fallire l'ingest su Qdrant.
    synced = 0
    try:
        from . import docstore
        synced = docstore.sync_notes(notes_meta)
    except Exception:
        import logging
        logging.getLogger("ember.ingest").exception("sync documents Supabase fallito (ignorato)")

    return {"notes": n_notes, "chunks": len(points), "documents_synced": synced}


# ── Re-ingest INCREMENTALE (una o poche note) ─────────────────────────────────
# Fase 5 / connettore realtime: quando arriva/cambia contenuto, si re-indicizzano
# SOLO le note toccate invece dell'intero vault. Niente azzeramento della
# collection: per ogni nota si cancellano i suoi punti (filtro per `path`) e si
# ricaricano i chunk aggiornati. Path sparito/fuori-scope → sola rimozione.
def _is_note(rel: Path) -> bool:
    if any(p in SKIP_DIRS or p.startswith(".") for p in rel.parts):
        return False
    return rel.suffix == ".md" and rel.stem != "_index"


def _points_for_note(md: Path, rel: Path):
    """(points, note_meta) per UNA nota; None se la nota è vuota. Rete solo in embed()."""
    meta, body = _parse_note(md)
    body = body.strip()
    if not body:
        return [], None
    seg = segments_for(rel)
    title = meta.get("title", md.stem)
    tags = meta.get("tags", "")
    note_meta = {
        "org": seg["org"], "tenant": seg["tenant"], "sub_tenant": seg["sub_tenant"],
        "slug": md.stem, "title": title, "path": str(rel), "tags": tags, "content": body,
    }
    chunks = chunk(body)
    vectors = embed(chunks)
    points = [
        PointStruct(
            id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{rel}::{ci}")), vector=v,
            payload={"scope": seg["tenant"], "org": seg["org"], "tenant": seg["tenant"],
                     "sub_tenant": seg["sub_tenant"], "slug": md.stem, "title": title,
                     "path": str(rel), "tags": tags, "chunk": ci, "text": ch},
        )
        for ci, (ch, v) in enumerate(zip(chunks, vectors))
    ]
    return points, note_meta


def _delete_by_path(c: QdrantClient, rel: Path) -> None:
    c.delete(
        settings.qdrant_collection,
        points_selector=Filter(must=[FieldCondition(key="path", match=MatchValue(value=str(rel)))]),
        wait=True,
    )


def reindex_paths(paths, sync: bool = True) -> dict:
    """Re-ingest incrementale di note specifiche (path relativi al vault). NON azzera
    la collection: cancella+ricarica solo le note indicate; il resto resta intatto.
    `sync=False` salta il git pull (usalo subito dopo una scrittura locale, es. writeback,
    per non rischiare di sovrascrivere la nota appena creata)."""
    if not settings.vault_path:
        raise RuntimeError("VAULT_PATH non impostato nel .env")
    if sync:
        sync_vault(settings.vault_path, settings.vault_git_url, settings.vault_git_token)
    vault = Path(settings.vault_path)
    c = client()
    ensure_collection(c, fresh=False)          # crea se manca, MAI azzera
    indexed = removed = n_chunks = 0
    notes_meta = []
    for path in (paths or []):
        rel = Path(str(path))
        if rel.is_absolute() or ".." in rel.parts:   # sicurezza: mai fuori dal vault
            continue
        _delete_by_path(c, rel)                 # rimuove i punti vecchi (update/shrink/delete)
        md = vault / rel
        if not (md.exists() and _is_note(rel)):
            removed += 1
            continue
        points, note_meta = _points_for_note(md, rel)
        if not points:
            removed += 1
            continue
        c.upsert(settings.qdrant_collection, points=points, wait=True)
        indexed += 1
        n_chunks += len(points)
        notes_meta.append(note_meta)
    synced = 0
    if notes_meta:
        try:
            from . import docstore
            synced = docstore.sync_notes(notes_meta)
        except Exception:
            log.exception("sync documents Supabase fallito (ignorato)")
    return {"mode": "incremental", "indexed": indexed, "removed": removed,
            "chunks": n_chunks, "documents_synced": synced}


if __name__ == "__main__":
    print(run())
