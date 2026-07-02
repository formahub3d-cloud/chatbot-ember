"""API del servizio Ember.

Endpoint:
  GET  /health            stato e provider attivi
  POST /ingest            (admin) reindicizza il cervello su Qdrant
  POST /chat              (tenant) domanda → risposta limitata allo scope del tenant
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

from fastapi import FastAPI, HTTPException, Header, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .config import settings
from . import ingest, rag, ocr, extract, tenants

app = FastAPI(title="Ember — Cervello OVY", version="0.2.0")

# CORS: consente al widget di chat (browser) di chiamare l'API.
# I domini autorizzati arrivano da settings.cors_origins (vedi config.py):
# "*" per il pilota, oppure lista separata da virgola per la produzione.
_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()] or ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup_seed_tenants():
    """Se è collegato un database, crea/popola la tabella tenants alla partenza."""
    try:
        tenants.ensure_seeded()
    except Exception:
        log.exception("ensure_seeded fallito: si userà il fallback statico")


def tenant_or_401(key: str) -> dict:
    tenant = tenants.get_tenants().get(key)
    if not tenant:
        raise HTTPException(401, "Chiave tenant non valida")
    return tenant


class ChatIn(BaseModel):
    message: str


@app.get("/health")
def health():
    return {"status": "ok", "llm": settings.llm_provider, "embed": settings.embed_provider}


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
def do_chat(body: ChatIn, x_tenant_key: str = Header(default="")):
    tenant = tenant_or_401(x_tenant_key)
    if not rate_ok(x_tenant_key):
        raise HTTPException(429, "Troppe richieste. Riprova tra un minuto.")
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
