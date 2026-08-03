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
import os
import re
import subprocess
import threading
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


def sync_vault(vault_path: str, url: str, token: str = "", ref: str = "main") -> bool:
    """Aggiorna il vault locale dal repo git PRIMA dell'ingest. Funzione pura/testabile.

    - `url` vuoto → no-op, ritorna False (comportamento storico: legge la cartella locale).
    - `<vault_path>/.git` esiste → `git fetch --depth 1` + `git reset --hard FETCH_HEAD`.
    - altrimenti → `git clone --depth 1 <url> <vault_path>`.

    FIX A0 (vault stantio, 29-07): la vecchia via era `pull --ff-only`, che su un
    clone shallow fallisce con facilità; il fallimento veniva LOGGATO e si proseguiva
    con la copia locale — così la produzione ha reindicizzato per settimane la stessa
    fotografia del primo clone, con tutti i segnali del successo. Ora:
    - la via primaria è fetch+reset: funziona sugli shallow, è DETERMINISTICA
      (il vault locale coincide col remoto, sempre) e NON tocca i file non
      tracciati/gitignorati — che qui sono dati del cliente (contratti/, note
      private del write-back) e non vanno MAI persi;
    - se fetch+reset fallisce → UNA ripartenza con clone pulito in cartella nuova
      (_fresh_clone_swap, che trasloca il contenuto solo-locale prima dello swap);
    - se anche il clone fallisce → RuntimeError, come il clone iniziale: MAI più
      proseguire in silenzio su una copia che non si sa quanto sia vecchia.

    Usa subprocess con LISTA di argomenti (mai shell=True). Il token per repo privato è
    iniettato nell'URL (x-access-token) e non viene MAI loggato: nei log compare solo
    l'URL redatto. Ritorna True se ha sincronizzato.
    """
    if not url:
        return False
    with _GIT:
        return _sync_vault_locked(vault_path, url, token, ref)


# V10/A2: da adesso due percorsi diversi possono chiedere il vault — la ingest e
# il recupero del clone all'avvio. `_fresh_clone_swap` rinomina la cartella: due
# git in parallelo sulla stessa directory sono il modo più veloce di ritrovarsi
# con mezzo vault. Il lock copre SOLO le operazioni git, non la lettura delle
# note: serializzare un ingest intero bloccherebbe l'avvio del motore.
_GIT = threading.RLock()


def _sync_vault_locked(vault_path: str, url: str, token: str, ref: str) -> bool:
    vp = Path(vault_path)
    safe = _redact_url(url)
    if (vp / ".git").exists():
        try:
            subprocess.run(["git", "-C", str(vp), "fetch", "--depth", "1",
                            _authed_url(url, token), ref],
                           check=True, capture_output=True, text=True)
            subprocess.run(["git", "-C", str(vp), "reset", "--hard", "FETCH_HEAD"],
                           check=True, capture_output=True, text=True)
            log.info("vault: fetch+reset ok (%s)", safe)
        except (subprocess.CalledProcessError, OSError) as e:
            log.warning("vault: fetch+reset fallito (%s): %s — riprovo con un clone pulito",
                        safe, _redact_url(str(e)))
            _fresh_clone_swap(vp, url, token, safe, ref)  # solleva se fallisce anche lui
        return True
    vp.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(["git", "clone", "--depth", "1", "--branch", ref,
                        _authed_url(url, token), str(vp)],
                       check=True, capture_output=True, text=True)
        log.info("vault: git clone --depth 1 --branch %s ok (%s → %s)", ref, safe, vp)
    except (subprocess.CalledProcessError, OSError) as e:
        # nessuna copia locale da cui ripartire: senza vault non c'è ingest → errore chiaro.
        log.error("vault: git clone fallito (%s): %s", safe, _redact_url(str(e)))
        raise RuntimeError(f"Impossibile clonare il vault da {safe}") from e
    return True


def _fresh_clone_swap(vp: Path, url: str, token: str, safe: str, ref: str = "main") -> None:
    """Ripartenza pulita quando fetch+reset fallisce: clone in una cartella NUOVA,
    trasloco del contenuto SOLO-LOCALE (gitignorato: `contratti/` annidati, note
    private del write-back — dati del cliente, mai perderli), poi swap atomico
    per rename. Se il clone fallisce → RuntimeError: mai indicizzare una copia
    di cui non si conosce l'età."""
    import shutil
    tmp = vp.parent / (vp.name + ".fresh")
    stale = vp.parent / (vp.name + ".stale")
    shutil.rmtree(tmp, ignore_errors=True)
    try:
        subprocess.run(["git", "clone", "--depth", "1", "--branch", ref,
                        _authed_url(url, token), str(tmp)],
                       check=True, capture_output=True, text=True)
    except (subprocess.CalledProcessError, OSError) as e:
        log.error("vault: anche il clone pulito è fallito (%s): %s", safe, _redact_url(str(e)))
        raise RuntimeError(
            f"Vault non sincronizzabile da {safe}: né fetch+reset né un clone pulito "
            "sono riusciti. Ingest interrotto: MAI indicizzare in silenzio una copia "
            "locale di età ignota (fix A0).") from e
    # trasloco RICORSIVO di ogni file presente solo nella copia vecchia (fuori da
    # .git): copre i gitignorati ovunque siano annidati.
    for root, dirs, files in os.walk(vp):
        rel_root = Path(root).relative_to(vp)
        if ".git" in rel_root.parts or rel_root.name == ".git":
            dirs[:] = []
            continue
        dirs[:] = [d for d in dirs if d != ".git"]
        for f in files:
            src = Path(root) / f
            dst = tmp / rel_root / f
            if not dst.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dst))
    vp.rename(stale)
    tmp.rename(vp)
    shutil.rmtree(stale, ignore_errors=True)
    log.info("vault: clone pulito + swap ok (%s)", safe)


def procura_clone() -> dict:
    """V10/A2 · All'avvio: se il clone del vault non c'è, prenderlo.

    Ritorna `{fatto, motivo, vault_commit}` — mai un'eccezione: è chiamata dal
    boot, e un motore che non parte perché non è riuscito a clonare sarebbe un
    rimedio peggiore del guasto. Chi vuole sapere com'è andata lo legge da
    `degrado.per("allarme-commit")`, che guarda il risultato e non il tentativo.

    Non fa la ingest. Il perché sta in `main._startup_clone_vault`."""
    if not settings.vault_boot_clone:
        return {"fatto": False, "motivo": "spento (VAULT_BOOT_CLONE)", "vault_commit": ""}
    if not settings.vault_path or not settings.vault_git_url:
        return {"fatto": False, "motivo": "nessun repo del vault configurato",
                "vault_commit": ""}
    if vault_info().get("vault_commit"):
        return {"fatto": False, "motivo": "il clone c'era già",
                "vault_commit": vault_info()["vault_commit"]}
    if _GIT.acquire(blocking=False):    # una ingest sta già clonando: non due volte
        try:
            sync_vault(settings.vault_path, settings.vault_git_url,
                       settings.vault_git_token, settings.vault_git_ref)
        except Exception as e:
            log.warning("vault: recupero del clone all'avvio fallito (%s)", type(e).__name__)
            return {"fatto": False, "motivo": f"clone fallito: {type(e).__name__}",
                    "vault_commit": ""}
        finally:
            _GIT.release()
    else:
        return {"fatto": False, "motivo": "una sincronizzazione è già in corso",
                "vault_commit": ""}
    sha = vault_info().get("vault_commit", "")
    log.info("vault: clone recuperato all'avvio (%s)", sha or "?")
    return {"fatto": True, "motivo": "", "vault_commit": sha}


def vault_info(vault_path: str | None = None) -> dict:
    """Commit e data del vault locale — la SPIA del fix A0: senza questi due campi
    in /ingest e /admin/brain nessuno può accorgersi di un cervello stantio
    guardando. Dict vuoto se la cartella non è un repo git (dev locale)."""
    vp = Path(vault_path or settings.vault_path)
    if not (vp / ".git").exists():
        return {}
    try:
        out = subprocess.run(["git", "-C", str(vp), "log", "-1", "--format=%H|%cI"],
                             check=True, capture_output=True, text=True).stdout.strip()
        sha, date = out.split("|", 1)
        return {"vault_commit": sha[:12], "vault_commit_date": date}
    except Exception:
        return {}


# Cartelle non utili al chatbot (derivati, scratch, fonti grezze).
# 'contratti' è escluso PER DEFAULT (dati personali): per farli interrogare dal
# consulente, togli "contratti" da questo set quando hai DPA + region Qdrant UE a posto.
# Perimetro del cervello interrogabile — UNA lista sola, decisione di prodotto
# 29-07 (P0-bis parte 3): `workspace/` e `sources/` sono DENTRO (contengono i
# runbook: è esattamente ciò che si vuole poter chiedere a Divina); fuori
# restano template, bozze, artefatti generati, materiale legacy e SOPRATTUTTO
# `contratti/` (dati personali — esclusione NON negoziabile). La stessa lista
# vive nei generatori del vault (build*.py di ovy-cervello): se diverge, i due
# grafi non combaceranno mai.
# `human` (01-08): i dati di «Human · evoluzione» — salute, obiettivi, persona.
# Categoria SPECIALE nel GDPR: NON entrano mai in Qdrant (il motore gira in US
# West e la region Qdrant non è verificata). Il pannello li legge dal disco
# via /admin/human; Divina non ci risponde sopra finché Andrea non decide
# esplicitamente, e comunque DOPO la migrazione in Europa — non prima.
SKIP_DIRS = {".git", ".obsidian", "_showcase", "_templates", "_bozze",
             "contratti", "human", "chatbot-jarvis", "chatbot-ember"}


def is_note_included(rel: Path) -> bool:
    """LA regola del perimetro, in un posto solo (usata da iter_notes, dal
    percorso incrementale e dallo script di parità scripts/count_notes.py).
    Oltre alle cartelle escluse: NIENTE note nella RADICE del vault (rilievo
    revisione 29-07 — README.md e simili sono metadati del repo, non
    conoscenza; e una nota in radice non ha org/tenant → nessuno scope
    sensato). `_index` restano fuori come sempre."""
    if rel.suffix != ".md" or rel.stem == "_index":
        return False
    if len(rel.parts) < 2:                     # file nella radice del vault
        return False
    return not any(p in SKIP_DIRS or p.startswith(".") for p in rel.parts)


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
REQUIRED_PAYLOAD_FIELDS = ("scope", "org", "tenant", "sub_tenant", "links")


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


def _parse_text(text: str):
    """Mini-parser frontmatter YAML (niente dipendenze esterne). Ritorna (meta, body)."""
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


def _parse_note(path: Path):
    return _parse_text(path.read_text("utf-8"))


# [[wikilink]] — la STESSA grammatica di brain._LINK_RE e del LINK_RE dei
# generatori del vault (alias '[[x|label]]' e ancore '[[x#sez]]' comprese).
# P0-bis parte 4: l'estrazione avviene sul testo COMPLETO del file, frontmatter
# INCLUSO — le liste di link nel frontmatter prima si perdevano perché il
# parser lo staccava prima dell'analisi.
_LINK_RE = re.compile(r"\[\[([^\]|#\n]+?)(?:[|#][^\]\n]*)?\]\]")


def wikilink_targets(full_text: str) -> list[str]:
    """Slug (normalizzati lowercase, deduplicati, in ordine) citati nel testo
    completo di una nota — frontmatter incluso."""
    seen, out = set(), []
    for m in _LINK_RE.finditer(full_text or ""):
        slug = m.group(1).strip().lower()
        if slug and slug not in seen:
            seen.add(slug)
            out.append(slug)
    return out


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
        if is_note_included(rel):
            yield md, rel


def run() -> dict:
    if not settings.vault_path:
        raise RuntimeError("VAULT_PATH non impostato nel .env")
    # Auto-ingest: se VAULT_GIT_URL è impostato, aggiorna il vault dal repo del cervello
    # PRIMA di leggerlo. Vuoto = no-op → legge la cartella locale (comportamento storico).
    sync_vault(settings.vault_path, settings.vault_git_url, settings.vault_git_token,
               settings.vault_git_ref)
    # GUARD anti-STANTIO (fix A0): dopo la sincronizzazione, l'età dell'ultimo
    # commit del vault deve stare sotto soglia — un vault fermo da giorni con la
    # sync «riuscita» è esattamente il falso-successo che ha portato in
    # produzione un cervello di settimane fa. PRIMA di ogni chiamata di rete.
    vinfo = vault_info()
    if settings.ingest_max_vault_age_h > 0 and vinfo.get("vault_commit_date"):
        from datetime import datetime, timezone
        try:
            dt = datetime.fromisoformat(vinfo["vault_commit_date"])
            age_h = (datetime.now(timezone.utc) - dt).total_seconds() / 3600
        except ValueError:
            age_h = -1
        if age_h > settings.ingest_max_vault_age_h:
            raise RuntimeError(
                f"ingest annullato: il vault è fermo al commit {vinfo['vault_commit']} "
                f"di ~{age_h:.0f} ore fa (soglia {settings.ingest_max_vault_age_h}h, "
                "INGEST_MAX_VAULT_AGE_H; 0 per disattivare). Se il vault è davvero "
                "fermo per scelta, alza la soglia; altrimenti la sincronizzazione "
                "non sta portando gli aggiornamenti.")
    vault = Path(settings.vault_path)
    c = client()

    # 1) Raccogli TUTTI i chunk + metadati (nessuna chiamata di rete qui).
    metas: list[dict] = []
    texts: list[str] = []
    notes_meta: list[dict] = []   # una voce per NOTA (per il sync metadati su Supabase)
    n_notes = 0
    for md, rel in iter_notes(vault):
        raw = md.read_text("utf-8")
        meta, body = _parse_text(raw)
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
            "raw": raw,        # testo COMPLETO (frontmatter incluso) per il grafo
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

    # GUARD anti-svuotamento (P0-bis parte 2, sintesi 29-07): se il vault è
    # mancante o incompleto (clone fallito, cartella sbagliata, disco vuoto)
    # la scansione NON solleva eccezioni — restituisce zero note. Senza questo
    # controllo il passo 3 azzererebbe comunque la collection: cervello
    # svuotato, nessun errore, exit code zero. Sotto soglia si INTERROMPE
    # PRIMA di ogni chiamata di rete e la collection esistente resta intatta.
    if n_notes < settings.ingest_min_notes:
        raise RuntimeError(
            f"ingest annullato: trovate solo {n_notes} note nel vault "
            f"(soglia minima {settings.ingest_min_notes}, INGEST_MIN_NOTES). "
            "La collection esistente NON è stata toccata. Vault mancante, "
            "clone fallito o percorso sbagliato?")

    # P0-bis parte 4: i [[link]] risolti diventano il campo `links` di OGNI
    # frammento della nota. Risoluzione sull'insieme degli slug reali:
    # link rotti e auto-riferimenti scartati in silenzio, archi deduplicati.
    # Forma UNICA dei link (rilievo revisione 29-07): slug MINUSCOLI ovunque,
    # identica al percorso incrementale — la stessa nota deve avere lo stesso
    # campo `links` da qualunque percorso sia stata indicizzata.
    slug_lower = {n["slug"].lower() for n in notes_meta}
    links_by_slug: dict[str, list[str]] = {}
    for n in notes_meta:
        me = n["slug"].lower()
        resolved = sorted({t for t in wikilink_targets(n["raw"])
                           if t in slug_lower and t != me})
        links_by_slug[n["slug"]] = resolved
        n["links"] = resolved
    for m in metas:
        m["links"] = links_by_slug.get(m["slug"], [])

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
                      "slug", "title", "path", "tags", "chunk", "text", "links")},
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

    # 5) Grafo del cervello (best-effort): nodi = note, sinapsi = [[link]] reali —
    #    alimenta la tab «Cervello vivo» della console (db/ovyon_graph.sql).
    graph_links = 0
    try:
        from . import brain
        graph_links = brain.save_graph(notes_meta)
    except Exception:
        import logging
        logging.getLogger("ember.ingest").exception("grafo cervello non aggiornato (ignorato)")

    # 6) V5b · Punto 9: registra il COMMIT appena letto — l'allarme del
    #    pannello confronta questo con vault_info(), non le ore. Best-effort.
    try:
        from . import brain
        brain.set_ingest_commit(vinfo.get("vault_commit", ""))
    except Exception:
        import logging
        logging.getLogger("ember.ingest").exception("commit ingest non registrato (ignorato)")

    # Fix A0: commit e data del vault SEMPRE nella risposta — «cervello
    # allineato al commit X del giorno Y», verificabile a occhio.
    return {"notes": n_notes, "chunks": len(points), "documents_synced": synced,
            "graph_links": graph_links, **vinfo}


# ── Re-ingest INCREMENTALE (una o poche note) ─────────────────────────────────
# Fase 5 / connettore realtime: quando arriva/cambia contenuto, si re-indicizzano
# SOLO le note toccate invece dell'intero vault. Niente azzeramento della
# collection: per ogni nota si cancellano i suoi punti (filtro per `path`) e si
# ricaricano i chunk aggiornati. Path sparito/fuori-scope → sola rimozione.
def _is_note(rel: Path) -> bool:
    return is_note_included(rel)               # UNA regola sola, mai due copie


def _points_for_note(md: Path, rel: Path):
    """(points, note_meta) per UNA nota; None se la nota è vuota. Rete solo in embed()."""
    raw = md.read_text("utf-8")
    meta, body = _parse_text(raw)
    body = body.strip()
    if not body:
        return [], None
    seg = segments_for(rel)
    title = meta.get("title", md.stem)
    tags = meta.get("tags", "")
    # Nel percorso INCREMENTALE non abbiamo l'insieme completo degli slug, quindi
    # i target NON vengono filtrati sui link rotti (lo fa l'ingest completo, che
    # rigenera anche il grafo). FORMA identica al percorso completo (rilievo
    # revisione 29-07): minuscoli, dedup, ordinati — così la stessa nota ha lo
    # stesso campo `links` da qualunque percorso sia stata indicizzata.
    links = sorted({t for t in wikilink_targets(raw) if t != md.stem.lower()})
    note_meta = {
        "org": seg["org"], "tenant": seg["tenant"], "sub_tenant": seg["sub_tenant"],
        "slug": md.stem, "title": title, "path": str(rel), "tags": tags, "content": body,
        "raw": raw, "links": links,
    }
    chunks = chunk(body)
    vectors = embed(chunks)
    points = [
        PointStruct(
            id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{rel}::{ci}")), vector=v,
            payload={"scope": seg["tenant"], "org": seg["org"], "tenant": seg["tenant"],
                     "sub_tenant": seg["sub_tenant"], "slug": md.stem, "title": title,
                     "path": str(rel), "tags": tags, "chunk": ci, "text": ch,
                     "links": links},
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
        sync_vault(settings.vault_path, settings.vault_git_url, settings.vault_git_token,
                   settings.vault_git_ref)
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
