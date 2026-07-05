"""API del servizio Ember.

Endpoint:
  GET  /health            stato e provider attivi
  POST /ingest            (admin) reindicizza il cervello su Qdrant
  POST /chat              (tenant) domanda → risposta limitata allo scope del tenant
                          con {"stream": true} risposta SSE token per token
  POST /upload            (tenant) carica un contratto → OCR + estrazione → ANTEPRIMA
                          dei campi (NON consolida: richiede conferma umana)
  POST /contract/confirm  (tenant) consolida i campi CONFERMATI → nota nel vault
                          + riga nel database Notion (write-back Fase 2b)
"""
import json
import logging
import os
import tempfile
import time
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("ember")

# Rate limiting in memoria: finestra scorrevole di 60s per chiave tenant.
# Per produzione multi-istanza si passerà a Redis (vedi roadmap).
_hits: dict = {}


def rate_ok(key: str) -> bool:
    limit = settings.rate_limit_per_min
    if limit <= 0:
        return True
    now = time.time()
    dq = _hits.setdefault(key, deque())
    while dq and now - dq[0] > 60:
        dq.popleft()
    if len(dq) >= limit:
        return False
    dq.append(now)
    return True

from fastapi import FastAPI, HTTPException, Header, UploadFile, File, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config import settings
from . import ingest, rag, ocr, extract, tenants, security, voice, writeback

_DEFAULT_ADMIN_TOKENS = {"", "change-me", "cambia-questo-token-admin"}


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Allo startup: avvisa se i secret sono ai default e — se è collegato un
    database — crea/popola la tabella tenants."""
    if settings.admin_token in _DEFAULT_ADMIN_TOKENS:
        log.warning("ADMIN_TOKEN è al valore di default: cambialo in produzione "
                    "(l'endpoint /ingest è protetto da un token noto).")
    try:
        tenants.ensure_seeded()
    except Exception:
        log.exception("ensure_seeded fallito: si userà il fallback statico")
    yield


app = FastAPI(title="Ember — Cervello OVY", version="0.3.0", lifespan=_lifespan)

# CORS: consente al widget di chat (browser) di chiamare l'API.
# I domini autorizzati arrivano da settings.cors_origins (vedi config.py):
# "*" per il pilota, oppure lista separata da virgola per la produzione.
# Difesa aggiuntiva per-tenant: ogni tenant può avere "allowed_origins" e la
# richiesta viene rifiutata (403) se l'Origin non è consentito (vedi /chat).
_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()] or ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.middleware("http")
async def _security_headers(request: Request, call_next):
    """Header di sicurezza su ogni risposta + trasparenza AI (EU AI Act)."""
    resp = await call_next(request)
    if settings.security_headers:
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        resp.headers.setdefault("Permissions-Policy", "geolocation=(), camera=()")
        resp.headers.setdefault("X-AI-Generated", "true")
    return resp


# Widget servito dal backend stesso: un solo file da mantenere, stesso dominio
# dell'API, aggiornato a ogni deploy. → https://<dominio>/widget/embed.js
app.mount("/widget", StaticFiles(directory="widget"), name="widget")


def tenant_or_401(key: str) -> dict:
    tenant = tenants.get_tenant_by_key(key)
    if not tenant:
        raise HTTPException(401, "Chiave tenant non valida")
    return tenant


def _grants(tenant: dict) -> dict:
    """Grant del tenant per il retrieval. `allowed_scopes` (storico, livello tenant)
    resta il campo principale; `allowed_orgs` e `allowed_sub_tenants` sono opzionali
    e additivi (modello a tre livelli OVYON). Vedi rag.build_filter."""
    return {
        "allowed_scopes": tenant.get("allowed_scopes", []),
        "allowed_orgs": tenant.get("allowed_orgs", []),
        "allowed_sub_tenants": tenant.get("allowed_sub_tenants", []),
    }


class ChatIn(BaseModel):
    message: str
    stream: bool = False  # true → risposta SSE (text/event-stream) token per token
    history: list = []     # turni precedenti [{role, content}] dal client, per i follow-up


class SearchIn(BaseModel):
    message: str
    k: int = 6


class WritebackIn(BaseModel):
    scope: str                 # tenant/scope di destinazione (deve essere concesso)
    title: str
    body: str
    summary: str = ""
    tags: list[str] = []
    confirm: bool = False      # false → solo ANTEPRIMA (regola 5: conferma umana)
    overwrite: bool = False


class ContractConfirmIn(BaseModel):
    cliente: str = "ats"           # tenant/scope di destinazione (deve essere concesso)
    fields: dict = {}              # campi confermati dall'utente (CF, codice, date, tipologia)
    to_notion: bool = True         # spinge anche su Notion (no-op se non configurato)


def _guard(tenant: dict, key: str, origin: str) -> None:
    """Controlli comuni agli endpoint tenant: origine, rate limit, quota."""
    if not security.origin_allowed(origin, tenant.get("allowed_origins")):
        raise HTTPException(403, "Origine non autorizzata per questo tenant.")
    if not rate_ok(key):
        raise HTTPException(429, "Troppe richieste. Riprova tra un minuto.")
    if not tenants.quota_ok(tenant):
        raise HTTPException(429, "Quota giornaliera superata per questo tenant.")


@app.get("/health")
def health():
    return {"status": "ok", "llm": settings.llm_provider, "embed": settings.embed_provider,
            "voice": settings.voice_provider or "browser"}


@app.get("/config")
def config(x_tenant_key: str = Header(default="")):
    """Branding + capacità per il widget (titolo, accent, voce disponibile).
    Permette al widget di auto-configurarsi dal server senza ripetere i dati nell'HTML."""
    tenant = tenant_or_401(x_tenant_key)
    brand = tenant.get("branding", {}) or {}
    return {
        "title": brand.get("title", tenant.get("name", "Ember · Assistente")),
        "subtitle": brand.get("subtitle", "Assistente AI"),
        "accent": brand.get("accent", "#0ED4E4"),
        "voice_pro": voice.stt_enabled(),   # true → il widget può usare la voce PRO via proxy
    }


class TTSIn(BaseModel):
    text: str


@app.post("/voice/stt")
async def do_stt(file: UploadFile = File(...), x_tenant_key: str = Header(default="")):
    """Audio → testo (voce PRO). 501 se VOICE_PROVIDER non è configurato."""
    tenant_or_401(x_tenant_key)
    if not voice.stt_enabled():
        raise HTTPException(501, "Voce PRO non attiva: usa la voce del browser.")
    audio = await file.read()
    try:
        return {"text": voice.transcribe(audio, mime=file.content_type or "audio/webm")}
    except Exception:
        log.exception("stt failed")
        raise HTTPException(502, "Trascrizione non riuscita.")


@app.post("/voice/tts")
def do_tts(body: TTSIn, x_tenant_key: str = Header(default="")):
    """Testo → audio (voce PRO). 501 se VOICE_PROVIDER non è configurato."""
    tenant_or_401(x_tenant_key)
    if not voice.tts_enabled():
        raise HTTPException(501, "Voce PRO non attiva: usa la voce del browser.")
    text = security.cap_input(body.text, settings.max_message_chars)
    if not text:
        raise HTTPException(422, "Testo vuoto.")
    try:
        audio, ctype = voice.synthesize(text)
        return Response(content=audio, media_type=ctype)
    except Exception:
        log.exception("tts failed")
        raise HTTPException(502, "Sintesi vocale non riuscita.")


@app.post("/ingest")
def do_ingest(authorization: str = Header(default="")):
    if authorization != f"Bearer {settings.admin_token}":
        raise HTTPException(401, "Token admin non valido")
    try:
        return ingest.run()
    except HTTPException:
        raise
    except Exception:
        log.exception("ingest failed")
        raise HTTPException(500, "Errore interno durante l'indicizzazione.")


@app.post("/chat")
def do_chat(body: ChatIn, x_tenant_key: str = Header(default=""), origin: str = Header(default="")):
    """Risposta del chatbot. Con {"stream": true} nel body la risposta è SSE:
    `event: sources` (fonti+scope) → N × `data: {"delta": ...}` → `event: done`.
    Senza flag resta il JSON classico {answer, sources, scopes} (retro-compat)."""
    tenant = tenant_or_401(x_tenant_key)
    if not security.origin_allowed(origin, tenant.get("allowed_origins")):
        raise HTTPException(403, "Origine non autorizzata per questo tenant.")
    if not rate_ok(x_tenant_key):
        raise HTTPException(429, "Troppe richieste. Riprova tra un minuto.")
    if not tenants.quota_ok(tenant):
        raise HTTPException(429, "Quota giornaliera superata per questo tenant.")
    body.message = security.cap_input(body.message, settings.max_message_chars)
    if not body.message:
        raise HTTPException(422, "Messaggio vuoto.")
    log.info("chat tenant=%s q=%r", tenant.get("name", "?"), security.redact_pii(body.message)[:200])
    if body.stream:
        try:
            gen = rag.answer_stream(body.message, _grants(tenant), history=body.history)
            first = next(gen)  # forza retrieval/validazione PRIMA degli header 200
        except HTTPException:
            raise
        except Exception:
            log.exception("chat stream failed")
            raise HTTPException(500, "Errore interno del chatbot.")

        def _stream():
            yield first
            try:
                yield from gen
            except Exception:
                log.exception("chat stream interrotto")
                yield 'event: error\ndata: {"message": "Stream interrotto."}\n\n'

        return StreamingResponse(
            _stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    try:
        return rag.answer(body.message, _grants(tenant), history=body.history)
    except HTTPException:
        raise
    except Exception:
        log.exception("chat failed")
        raise HTTPException(500, "Errore interno del chatbot.")


# ── Endpoint per il connettore MCP (ovy_search / get_document / list_context /
#    create|update_document). Stessa autenticazione e stessi filtri per grant del
#    /chat: l'isolamento è server-side, non delegato al connettore. ──────────────

@app.post("/search")
def do_search(body: SearchIn, x_tenant_key: str = Header(default=""), origin: str = Header(default="")):
    """ovy_search: risultati rilevanti (metadati + snippet) nello scope del tenant."""
    tenant = tenant_or_401(x_tenant_key)
    _guard(tenant, x_tenant_key, origin)
    q = security.cap_input(body.message, settings.max_message_chars)
    if not q:
        raise HTTPException(422, "Query vuota.")
    k = max(1, min(int(body.k or 6), 20))
    tenants.log_access(tenant.get("key_hash"), "read", detail="search")
    try:
        return rag.search(q, _grants(tenant), k)
    except Exception:
        log.exception("search failed")
        raise HTTPException(500, "Errore interno durante la ricerca.")


@app.get("/document")
def do_document(slug: str, x_tenant_key: str = Header(default=""), origin: str = Header(default="")):
    """ovy_get_document: contenuto completo di una nota per slug, se nello scope."""
    tenant = tenant_or_401(x_tenant_key)
    _guard(tenant, x_tenant_key, origin)
    try:
        doc = rag.get_document(slug, _grants(tenant))
    except Exception:
        log.exception("get_document failed")
        raise HTTPException(500, "Errore interno.")
    if not doc:
        raise HTTPException(404, "Nota non trovata o fuori dallo scope.")
    tenants.log_access(tenant.get("key_hash"), "read", detail=f"document:{slug}")
    return doc


@app.get("/context")
def do_context(x_tenant_key: str = Header(default=""), origin: str = Header(default="")):
    """ovy_list_context: livelli di permesso (org/tenant/sub) visibili al tenant."""
    tenant = tenant_or_401(x_tenant_key)
    _guard(tenant, x_tenant_key, origin)
    return {"name": tenant.get("name", ""), **rag.list_context(_grants(tenant))}


@app.post("/writeback")
def do_writeback(body: WritebackIn, x_tenant_key: str = Header(default=""), origin: str = Header(default="")):
    """ovy_create_document / ovy_update_document: scrive una nota nel vault, MA solo
    dopo conferma umana (confirm=true). Senza conferma restituisce l'anteprima.
    Lo scope di destinazione deve essere tra quelli concessi al tenant."""
    tenant = tenant_or_401(x_tenant_key)
    _guard(tenant, x_tenant_key, origin)
    grants = _grants(tenant)
    ctx = rag.list_context(grants)
    if not ctx["master"] and body.scope not in (ctx["allowed_tenants"] or []):
        raise HTTPException(403, "Scope di destinazione non consentito per questo tenant.")
    title = security.cap_input(body.title, 200)
    if not title:
        raise HTTPException(422, "Titolo vuoto.")
    if not body.confirm:
        preview = writeback.render_note(body.scope, title, body.body, body.summary, body.tags)
        return {"consolidato": False, "preview": preview,
                "note": "Conferma con confirm=true per scrivere nel vault."}
    try:
        res = writeback.save_note(body.scope, title, body.body, body.summary,
                                  body.tags, overwrite=body.overwrite)
    except Exception:
        log.exception("writeback failed")
        raise HTTPException(500, "Errore durante la scrittura della nota.")
    if res.get("created"):
        tenants.log_access(tenant.get("key_hash"), "update" if body.overwrite else "create",
                           tenant_code=body.scope, detail=res.get("path"))
    return {"consolidato": res.get("created", False), **res}


@app.post("/upload")
async def do_upload(file: UploadFile = File(...), x_tenant_key: str = Header(default=""),
                    origin: str = Header(default="")):
    """Carica un documento → OCR → estrazione campi → ANTEPRIMA da confermare.
    Il consolidamento (write-back su vault/Notion) avviene solo dopo conferma umana.
    """
    tenant = tenant_or_401(x_tenant_key)
    _guard(tenant, x_tenant_key, origin)
    data = await file.read()
    if not data:
        raise HTTPException(422, "File vuoto.")
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(413, f"File troppo grande (max {settings.max_upload_bytes // 1_000_000} MB).")
    suffix = Path(file.filename or "doc.pdf").suffix or ".pdf"
    fd, tmp_path = tempfile.mkstemp(suffix=suffix)
    try:
        with os.fdopen(fd, "wb") as tmp:
            tmp.write(data)
        mime = file.content_type or "application/pdf"
        try:
            text = ocr.ocr_document(tmp_path, mime=mime)
        except Exception:
            log.exception("upload/ocr failed")
            raise HTTPException(502, "OCR non riuscito sul documento.")
        fields = extract.extract_unilav(text)
    finally:
        try:
            os.remove(tmp_path)   # il file temporaneo non deve mai restare su disco
        except OSError:
            pass
    return {"preview": fields, "note": "Conferma i campi prima del consolidamento.",
            "consolidato": False}


@app.post("/contract/confirm")
def do_contract_confirm(body: ContractConfirmIn, x_tenant_key: str = Header(default=""),
                        origin: str = Header(default="")):
    """Consolida un contratto DOPO la conferma umana dei campi (regola 5): scrive la
    nota nel vault (cartella privata gitignorata) e — se to_notion e la config Notion
    sono attive — inserisce la riga nel database contratti. Lo scope di destinazione
    (cliente) deve essere tra quelli concessi al tenant. È il passo di consolidamento
    del flusso /upload → anteprima → conferma."""
    tenant = tenant_or_401(x_tenant_key)
    _guard(tenant, x_tenant_key, origin)
    ctx = rag.list_context(_grants(tenant))
    if not ctx["master"] and body.cliente not in (ctx["allowed_tenants"] or []):
        raise HTTPException(403, "Scope di destinazione non consentito per questo tenant.")
    if not body.fields:
        raise HTTPException(422, "Nessun campo da consolidare.")
    try:
        path = writeback.save_contract_note(body.fields, cliente=body.cliente)
    except Exception:
        log.exception("save_contract_note failed")
        raise HTTPException(500, "Errore durante la scrittura della nota contratto.")
    out = {"consolidato": True, "vault_path": path}
    if body.to_notion:
        # backlink alla nota Obsidian nella riga Notion (campo "Nota Obsidian")
        out["notion"] = writeback.notion_upsert(dict(body.fields, slug=Path(path).stem))
    tenants.log_access(tenant.get("key_hash"), "create", tenant_code=body.cliente, detail=path)
    return out
