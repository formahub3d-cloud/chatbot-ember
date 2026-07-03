"""API del servizio Ember.

Endpoint:
  GET  /health            stato e provider attivi
  POST /ingest            (admin) reindicizza il cervello su Qdrant
  POST /chat              (tenant) domanda → risposta limitata allo scope del tenant
                          con {"stream": true} risposta SSE token per token
  POST /upload            (tenant) carica un contratto → OCR + estrazione → ANTEPRIMA
                          dei campi (NON consolida: richiede conferma umana)
"""
import json
import logging
import tempfile
import time
from collections import deque
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
from . import ingest, rag, ocr, extract, tenants, security, voice

app = FastAPI(title="Ember — Cervello OVY", version="0.3.0")

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


@app.on_event("startup")
def _startup_seed_tenants():
    """Se è collegato un database, crea/popola la tabella tenants alla partenza."""
    try:
        tenants.ensure_seeded()
    except Exception:
        log.exception("ensure_seeded fallito: si userà il fallback statico")


def tenant_or_401(key: str) -> dict:
    tenant = tenants.get_tenant_by_key(key)
    if not tenant:
        raise HTTPException(401, "Chiave tenant non valida")
    return tenant


class ChatIn(BaseModel):
    message: str
    stream: bool = False  # true → risposta SSE (text/event-stream) token per token


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
            gen = rag.answer_stream(body.message, tenant["allowed_scopes"])
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
        return rag.answer(body.message, tenant["allowed_scopes"])
    except HTTPException:
        raise
    except Exception:
        log.exception("chat failed")
        raise HTTPException(500, "Errore interno del chatbot.")


@app.post("/upload")
async def do_upload(file: UploadFile = File(...), x_tenant_key: str = Header(default="")):
    """Carica un documento → OCR → estrazione campi → ANTEPRIMA da confermare.
    Il consolidamento (write-back su vault/Notion) avviene solo dopo conferma umana.
    """
    tenant_or_401(x_tenant_key)
    suffix = Path(file.filename or "doc.pdf").suffix or ".pdf"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name
    mime = file.content_type or "application/pdf"
    text = ocr.ocr_document(tmp_path, mime=mime)
    fields = extract.extract_unilav(text)
    return {"preview": fields, "note": "Conferma i campi prima del consolidamento.",
            "consolidato": False}
